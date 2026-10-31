import json
import frappe
from frappe import _


def get_default_company(company=None):
    if company and frappe.db.exists("Company", company):
        return company
    return frappe.db.get_single_value("Global Defaults", "default_company") or "ركن سبل الافق"


@frappe.whitelist()
def get_chart_of_accounts_tree(company=None):
    """
    Returns the live Chart of Accounts tree structure for the company.
    Includes account name, parent account, root type, account type, is_group flag,
    and current balance.
    """
    comp = get_default_company(company)
    accounts = frappe.get_all(
        "Account",
        filters={"company": comp, "disabled": 0},
        fields=[
            "name",
            "account_name",
            "account_number",
            "parent_account",
            "root_type",
            "account_type",
            "is_group",
            "account_currency"
        ],
        order_by="root_type, account_number, name"
    )

    # Get balances for ledger accounts from GL Entry
    gl_balances = {}
    gl_data = frappe.db.sql(
        """
        SELECT account, SUM(debit - credit) as balance
        FROM `tabGL Entry`
        WHERE company = %s AND is_cancelled = 0
        GROUP BY account
        """,
        (comp,),
        as_dict=True
    )
    for row in gl_data:
        gl_balances[row.account] = float(row.balance or 0.0)

    account_list = []
    for acc in accounts:
        acc_dict = {
            "name": acc.name,
            "account_name": acc.account_name,
            "account_number": acc.account_number or "",
            "parent_account": acc.parent_account or "",
            "root_type": acc.root_type or "",
            "account_type": acc.account_type or "",
            "is_group": bool(acc.is_group),
            "currency": acc.account_currency or "SAR",
            "balance": gl_balances.get(acc.name, 0.0) if not acc.is_group else None
        }
        account_list.append(acc_dict)

    return {
        "company": comp,
        "total_accounts": len(account_list),
        "accounts": account_list
    }


@frappe.whitelist()
def get_cost_centers_tree(company=None):
    """
    Returns the live Cost Centers hierarchy for the company.
    """
    comp = get_default_company(company)
    cost_centers = frappe.get_all(
        "Cost Center",
        filters={"company": comp, "disabled": 0},
        fields=["name", "cost_center_name", "parent_cost_center", "is_group"],
        order_by="name"
    )
    return {
        "company": comp,
        "cost_centers": cost_centers
    }


@frappe.whitelist()
def get_projects_list(status=None, company=None):
    """
    Returns active or filtered projects with completion percentage and customer.
    """
    filters = {}
    if company:
        filters["company"] = company
    if status:
        filters["status"] = status

    projects = frappe.get_all(
        "Project",
        filters=filters,
        fields=["name", "project_name", "status", "customer", "percent_complete", "expected_end_date"],
        order_by="creation desc",
        limit=50
    )
    return {
        "projects": projects
    }


@frappe.whitelist()
def get_gl_balance(account=None, cost_center=None, project=None, from_date=None, to_date=None, company=None):
    """
    Calculates live GL balance (Debit, Credit, Net Balance) with optional filters
    for account, cost_center, project, and date range.
    """
    comp = get_default_company(company)
    conditions = ["company = %(company)s", "is_cancelled = 0"]
    values = {"company": comp}

    if account:
        conditions.append("account = %(account)s")
        values["account"] = account
    if cost_center:
        conditions.append("cost_center = %(cost_center)s")
        values["cost_center"] = cost_center
    if project:
        conditions.append("project = %(project)s")
        values["project"] = project
    if from_date:
        conditions.append("posting_date >= %(from_date)s")
        values["from_date"] = from_date
    if to_date:
        conditions.append("posting_date <= %(to_date)s")
        values["to_date"] = to_date

    where_clause = " AND ".join(conditions)
    query = f"""
        SELECT 
            SUM(debit) as total_debit, 
            SUM(credit) as total_credit, 
            SUM(debit - credit) as net_balance,
            COUNT(*) as entry_count
        FROM `tabGL Entry`
        WHERE {where_clause}
    """
    res = frappe.db.sql(query, values, as_dict=True)
    summary = res[0] if res else {"total_debit": 0, "total_credit": 0, "net_balance": 0, "entry_count": 0}

    return {
        "filters": values,
        "total_debit": float(summary.total_debit or 0.0),
        "total_credit": float(summary.total_credit or 0.0),
        "net_balance": float(summary.net_balance or 0.0),
        "entry_count": summary.entry_count or 0
    }


def _resolve_leaf_account(acc_identifier, comp):
    """
    Resolves an account identifier (name or account_name) to an active leaf account.
    If it's a group or not found, returns error information with suggestions.
    """
    # 1. Direct match on name
    acc = frappe.db.get_value(
        "Account",
        {"name": acc_identifier, "company": comp},
        ["name", "account_name", "is_group", "disabled", "parent_account", "account_type"],
        as_dict=True
    )

    # 2. Match on account_name if not found
    if not acc:
        acc = frappe.db.get_value(
            "Account",
            {"account_name": acc_identifier, "company": comp},
            ["name", "account_name", "is_group", "disabled", "parent_account", "account_type"],
            as_dict=True
        )

    # 3. Fuzzy search if still not found
    if not acc:
        suggestions = frappe.get_all(
            "Account",
            filters={"company": comp, "is_group": 0, "disabled": 0, "account_name": ["like", f"%{acc_identifier}%"]},
            fields=["name", "account_name", "parent_account"],
            limit=5
        )
        return False, {
            "status": "error",
            "message": f"الحساب '{acc_identifier}' غير موجود في شجرة الحسابات للشركة {comp}.",
            "suggested_accounts": suggestions
        }

    # 4. Check if disabled
    if acc.disabled:
        return False, {
            "status": "error",
            "message": f"الحساب '{acc.name}' معطل (Disabled) حالياً في النظام ولا يمكن إجراء حركات عليه."
        }

    # 5. Check if group account
    if acc.is_group:
        children = frappe.get_all(
            "Account",
            filters={"parent_account": acc.name, "company": comp, "is_group": 0, "disabled": 0},
            fields=["name", "account_name"],
            limit=10
        )
        if not children:
            # Check all descendants
            children = frappe.get_all(
                "Account",
                filters={"company": comp, "is_group": 0, "disabled": 0, "parent_account": ["like", f"%{acc.name}%"]},
                fields=["name", "account_name"],
                limit=10
            )
        return False, {
            "status": "error",
            "message": f"الحساب '{acc.name}' هو حساب رئيسي/تجميعي (Group Account) ولا يمكن إجراء قيود عليه مباشرة. يجب استخدام أحد الحسابات الفرعية التابعة له.",
            "recommended_leaf_accounts": children
        }

    return True, acc


@frappe.whitelist()
def create_draft_journal_entry(
    company=None,
    posting_date=None,
    debit_account=None,
    credit_account=None,
    amount=None,
    cost_center=None,
    project=None,
    user_remark=None,
    party_type=None,
    party=None
):
    """
    Creates a Draft Journal Entry (docstatus = 0) with a debit line and credit line.
    Fully hardened against Group Accounts and disabled accounts.
    Returns the created document name and direct clickable link URL.
    """
    comp = get_default_company(company)
    if not posting_date:
        posting_date = frappe.utils.today()

    if not debit_account:
        return {"status": "error", "message": "يجب تحديد الحساب المدين (debit_account)."}
    if not credit_account:
        return {"status": "error", "message": "يجب تحديد الحساب الدائن (credit_account)."}

    # Validate and resolve debit account
    ok_debit, debit_res = _resolve_leaf_account(debit_account, comp)
    if not ok_debit:
        return debit_res
    debit_doc = debit_res
    debit_account = debit_doc["name"]

    # Validate and resolve credit account
    ok_credit, credit_res = _resolve_leaf_account(credit_account, comp)
    if not ok_credit:
        return credit_res
    credit_doc = credit_res
    credit_account = credit_doc["name"]

    # Prevent identical debit and credit account
    if debit_account == credit_account:
        return {"status": "error", "message": f"لا يمكن أن يكون الحساب المدين والدائن متطابقين: '{debit_account}'."}

    # Validate amount
    try:
        amt = float(amount or 0.0)
        if amt <= 0:
            return {"status": "error", "message": "المبلغ يجب أن يكون أكبر من صفر."}
    except (ValueError, TypeError):
        return {"status": "error", "message": f"قيمة المبلغ غير صالحة: {amount}"}

    # Resolve default cost center if none provided
    if not cost_center:
        cost_center = frappe.db.get_value("Cost Center", {"company": comp, "is_group": 0}, "name")
    else:
        # Check cost center exists and is not group
        cc_info = frappe.db.get_value("Cost Center", cost_center, ["name", "is_group"], as_dict=True)
        if cc_info and cc_info.is_group:
            cost_center = frappe.db.get_value("Cost Center", {"company": comp, "is_group": 0, "parent_cost_center": cost_center}, "name") or cost_center

    # Verify project if provided
    if project and not frappe.db.exists("Project", project):
        proj = frappe.db.get_value("Project", {"project_name": project}, "name")
        project = proj if proj else None

    # Check party requirements for debit and credit accounts
    debit_party_type = None
    debit_party = None
    if debit_doc.get("account_type") in ["Receivable", "Payable"]:
        debit_party_type = party_type or ("Customer" if debit_doc.get("account_type") == "Receivable" else "Supplier")
        debit_party = party

    credit_party_type = None
    credit_party = None
    if credit_doc.get("account_type") in ["Receivable", "Payable"]:
        credit_party_type = party_type or ("Customer" if credit_doc.get("account_type") == "Receivable" else "Supplier")
        credit_party = party

    # Create Journal Entry
    je = frappe.new_doc("Journal Entry")
    je.voucher_type = "Journal Entry"
    je.company = comp
    je.posting_date = posting_date
    je.user_remark = user_remark or f"قيد تم إنشاؤه عبر المساعد الذكي Elsaidy AI"

    # Line 1: Debit
    debit_row = {
        "account": debit_account,
        "debit_in_account_currency": amt,
        "credit_in_account_currency": 0.0,
        "cost_center": cost_center,
        "project": project
    }
    if debit_party_type and debit_party:
        debit_row["party_type"] = debit_party_type
        debit_row["party"] = debit_party
    je.append("accounts", debit_row)

    # Line 2: Credit
    credit_row = {
        "account": credit_account,
        "debit_in_account_currency": 0.0,
        "credit_in_account_currency": amt,
        "cost_center": cost_center,
        "project": project
    }
    if credit_party_type and credit_party:
        credit_row["party_type"] = credit_party_type
        credit_row["party"] = credit_party
    je.append("accounts", credit_row)

    je.docstatus = 0  # Draft
    je.flags.ignore_permissions = True
    je.insert()
    frappe.db.commit()

    full_url = frappe.utils.get_url(f"/app/journal-entry/{je.name}")
    clean_message = (
        f"تم إنشاء مسودة قيد اليومية بنجاح:\n"
        f"📌 رقم القيد: {je.name}\n"
        f"💰 المبلغ: {amt:,.2f} ريال سعودي\n"
        f"🔹 الطرف المدين: {debit_account}\n"
        f"🔸 الطرف الدائن: {credit_account}\n"
        f"🏢 مركز التكلفة: {cost_center}\n\n"
        f"رابط عرض المستند المباشر:\n"
        f"{full_url}"
    )

    return {
        "status": "success",
        "journal_entry": je.name,
        "docstatus": 0,
        "posting_date": str(posting_date),
        "amount": amt,
        "debit_account": debit_account,
        "credit_account": credit_account,
        "cost_center": cost_center,
        "project": project,
        "url": full_url,
        "raw_url": full_url,
        "html_link": f'<a href="{full_url}" target="_blank">{je.name}</a>',
        "message": clean_message
    }


@frappe.whitelist()
def get_employee_info(employee=None, search_term=None):
    """
    Returns employee profile information (name, department, designation, status, date of joining).
    """
    filters = {}
    if employee:
        filters["name"] = employee
    elif search_term:
        filters["employee_name"] = ["like", f"%{search_term}%"]

    employees = frappe.get_all(
        "Employee",
        filters=filters,
        fields=[
            "name",
            "employee_name",
            "department",
            "designation",
            "status",
            "date_of_joining",
            "cell_number",
            "company_email"
        ],
        limit=20
    )
    return {"employees": employees}


@frappe.whitelist()
def get_leaves_summary(employee=None, status=None):
    """
    Returns leave applications summary.
    """
    filters = {}
    if employee:
        filters["employee"] = employee
    if status:
        filters["status"] = status

    leaves = frappe.get_all(
        "Leave Application",
        filters=filters,
        fields=["name", "employee", "employee_name", "leave_type", "from_date", "to_date", "total_leave_days", "status"],
        order_by="from_date desc",
        limit=20
    )
    return {"leaves": leaves}


@frappe.whitelist()
def get_warehouse_stock(item_code=None, warehouse=None):
    """
    Returns actual stock levels from tabBin for items and warehouses.
    """
    filters = {}
    if item_code:
        filters["item_code"] = item_code
    if warehouse:
        filters["warehouse"] = warehouse

    bins = frappe.get_all(
        "Bin",
        filters=filters,
        fields=["item_code", "warehouse", "actual_qty", "projected_qty", "reserved_qty"],
        order_by="actual_qty desc",
        limit=50
    )
    return {"stock": bins}


@frappe.whitelist()
def create_custody_settlement_entry(
    lines=None,
    custody_account=None,
    cost_center=None,
    project=None,
    user_remark=None,
    company=None,
    **kwargs
):
    """
    Allows accountant or site engineer to settle site custody in a single multi-line journal entry
    with automatic 15% VAT split for taxable expenses.
    """
    if not company or not frappe.db.exists("Company", company):
        user_comp = frappe.defaults.get_user_default("company")
        if user_comp and frappe.db.exists("Company", user_comp):
            company = user_comp
        else:
            comps = frappe.get_all("Company", pluck="name")
            company = comps[0] if comps else "ركن سبل الافق"

    if not lines:
        lines = kwargs.get("items") or kwargs.get("items_json") or kwargs.get("settlement_items")

    if not cost_center:
        cost_center = f"الرئيسي - {company}" if frappe.db.exists("Cost Center", f"الرئيسي - {company}") else None
        if not cost_center:
            ccs = frappe.get_all("Cost Center", filters={"company": company, "is_group": 0}, pluck="name", limit=1)
            cost_center = ccs[0] if ccs else None

    if not custody_account:
        custody_account = "1120 - عهد نقدية للمهندسين والمشرفين - Rkn"
        if not frappe.db.exists("Account", custody_account):
            custody_account = "1110 - النقدية في الصندوق - Rkn"

    # Parse lines if string
    if isinstance(lines, str):
        import json
        try:
            lines = json.loads(lines)
        except Exception:
            lines = []

    if not lines:
        return {
            "status": "error",
            "message": "لم يتم تمرير بنود التسوية أو لم يتم التعرف على بنود المصروفات."
        }

    input_vat_account = "1510 - ضريبة القيمة المضافة للمدخلات 15% - Rkn"
    posting_date = frappe.utils.today()

    je = frappe.new_doc("Journal Entry")
    je.voucher_type = "Journal Entry"
    je.company = company
    je.posting_date = posting_date
    je.user_remark = user_remark or f"تسوية عهدة موقع ميداني - {project or ''} - بواسطة مساعد Elsaidy AI"

    total_vat = 0.0
    breakdown_items = []

    # Process each expense line
    for idx, item in enumerate(lines, 1):
        desc = item.get("description") or f"بند تسوية رقم {idx}"
        amount = float(item.get("amount") or 0.0)
        if amount <= 0:
            continue

        acc = item.get("account")
        if not acc or not frappe.db.exists("Account", acc):
            d_lower = desc.lower()
            if any(k in d_lower for k in ["بنزين", "وقود", "ديزل", "محروقات", "بترول", "gasoline", "fuel"]):
                acc = "5120 - مصروف الوقود والمحروقات - Rkn"
            elif any(k in d_lower for k in ["صيانة", "إصلاح", "قطع غيار", "تصليح", "repair"]):
                acc = "5130 - صيانة وإصلاح السيارات والمعدات - Rkn"
            elif any(k in d_lower for k in ["إيجار معدات", "آليات", "بوكلين", "شاحنة", "كرين"]):
                acc = "5140 - إيجار معدات وآليات ثقيلة - Rkn"
            elif any(k in d_lower for k in ["مواد", "أسمنت", "رمل", "حديد", "بلك", "مهمات", "خشب", "مشتريات"]):
                acc = "5150 - مواد ومهمات تشغيل المشاريع - Rkn"
            elif any(k in d_lower for k in ["عمال", "يوميات", "مقاول", "أجور", "مصنعيات", "تعتيق"]):
                acc = "5160 - أعمال مقاولي الباطن - Rkn"
            elif any(k in d_lower for k in ["ضيافة", "إعاشة", "غداء", "عشاء", "شاي", "ماء", "قهوة"]):
                acc = "5170 - ضيافة وإعاشة مواقع - Rkn"
            elif any(k in d_lower for k in ["رسوم", "بلدية", "غرامة", "تصريح", "شهادة"]):
                acc = "5230 - رسوم حكومية وتراخيص بلدية - Rkn"
            else:
                acc = "5150 - مواد ومهمات تشغيل المشاريع - Rkn"

        is_taxable = item.get("is_taxable")
        if is_taxable is None:
            if acc in ["5160 - أعمال مقاولي الباطن - Rkn", "5230 - رسوم حكومية وتراخيص بلدية - Rkn"]:
                is_taxable = False
            else:
                is_taxable = True

        if is_taxable:
            base_amt = round(amount / 1.15, 2)
            vat_amt = round(amount - base_amt, 2)
            total_vat += vat_amt
        else:
            base_amt = round(amount, 2)
            vat_amt = 0.0

        je.append("accounts", {
            "account": acc,
            "debit_in_account_currency": base_amt,
            "credit_in_account_currency": 0.0,
            "cost_center": cost_center,
            "project": project,
            "user_remark": desc
        })

        breakdown_items.append({
            "desc": desc,
            "account": acc,
            "gross": amount,
            "base": base_amt,
            "vat": vat_amt
        })

    if total_vat > 0:
        if frappe.db.exists("Account", input_vat_account):
            je.append("accounts", {
                "account": input_vat_account,
                "debit_in_account_currency": round(total_vat, 2),
                "credit_in_account_currency": 0.0,
                "cost_center": cost_center,
                "project": project,
                "user_remark": "ضريبة القيمة المضافة للمدخلات 15% المستردة"
            })

    total_debits = sum(frappe.utils.flt(row.debit_in_account_currency) for row in je.accounts)
    je.append("accounts", {
        "account": custody_account,
        "debit_in_account_currency": 0.0,
        "credit_in_account_currency": total_debits,
        "cost_center": cost_center,
        "project": project,
        "user_remark": f"تسوية عهدة المهندس - إجمالي المبلغ: {total_debits:,.2f} ريال"
    })

    je.docstatus = 0
    je.flags.ignore_permissions = True
    je.insert()
    frappe.db.commit()

    full_url = frappe.utils.get_url(f"/app/journal-entry/{je.name}")

    msg_lines = [
        "تم إنشاء مسودة قيد تسوية العهدة بنجاح:",
        f"📌 رقم القيد: {je.name}",
        f"💰 إجمالي مبلغ التسوية: {total_debits:,.2f} ريال سعودي",
        f"🏢 حساب العهدة الدائن: {custody_account}",
        f"🔹 ضريبة المدخلات 15%: {total_vat:,.2f} ريال سعودي",
        "\nتفصيل بنود المصروفات المسواة:"
    ]
    for b in breakdown_items:
        tax_info = f"(أساس: {b['base']:,.2f} + ضريبة: {b['vat']:,.2f})" if b["vat"] > 0 else "(معفى/بدون ضريبة)"
        msg_lines.append(f"🔸 {b['desc']}: {b['gross']:,.2f} ريال {tax_info} ⬅ {b['account']}")

    msg_lines.append("\nرابط عرض قيد التسوية المباشر:")
    msg_lines.append(full_url)
    clean_msg = "\n".join(msg_lines)

    return {
        "status": "success",
        "journal_entry": je.name,
        "total_amount": total_debits,
        "total_vat": total_vat,
        "custody_account": custody_account,
        "url": full_url,
        "message": clean_msg
    }


@frappe.whitelist()
def get_project_financial_summary(project=None, company=None):
    """
    Returns an executive-level Arabic financial summary of a project or company-wide contracting operations:
    1. Total Cash & Bank Liquidity
    2. Project Revenues / Invoiced Value
    3. Project Direct Costs / Expenses
    4. Retentions held
    5. Net Margin / Profit
    6. VAT Position (Output VAT 2330 vs Input VAT 1510)
    """
    if not company or not frappe.db.exists("Company", company):
        user_comp = frappe.defaults.get_user_default("company")
        if user_comp and frappe.db.exists("Company", user_comp):
            company = user_comp
        else:
            comps = frappe.get_all("Company", pluck="name")
            company = comps[0] if comps else "ركن سبل الافق"

    cash_accounts = [
        "1110 - النقدية في الصندوق - Rkn",
        "1120 - عهد نقدية للمهندسين والمشرفين - Rkn"
    ]
    cash_balance = 0.0
    bank_balance = 0.0

    if frappe.db.exists("DocType", "GL Entry"):
        bank_accs = frappe.get_all("Account", filters={"company": company, "account_type": "Bank", "is_group": 0}, pluck="name")
        for ca in cash_accounts:
            if frappe.db.exists("Account", ca):
                res = frappe.db.sql("SELECT COALESCE(SUM(debit - credit), 0) FROM `tabGL Entry` WHERE account=%s AND is_cancelled=0", ca)
                if res and res[0][0]:
                    cash_balance += float(res[0][0])
        for ba in bank_accs:
            res = frappe.db.sql("SELECT COALESCE(SUM(debit - credit), 0) FROM `tabGL Entry` WHERE account=%s AND is_cancelled=0", ba)
            if res and res[0][0]:
                bank_balance += float(res[0][0])

    total_liquidity = cash_balance + bank_balance

    total_revenue = 0.0
    if frappe.db.exists("DocType", "Sales Invoice"):
        if project:
            res = frappe.db.sql(
                "SELECT COALESCE(SUM(base_grand_total), 0) FROM `tabSales Invoice` WHERE company=%s AND docstatus=1 AND project=%s",
                (company, project)
            )
        else:
            res = frappe.db.sql(
                "SELECT COALESCE(SUM(base_grand_total), 0) FROM `tabSales Invoice` WHERE company=%s AND docstatus=1",
                company
            )
        if res and res[0][0]:
            total_revenue = float(res[0][0])

    total_expenses = 0.0
    gl_filters = "WHERE gl.is_cancelled=0 AND acc.root_type='Expense'"
    params = []
    if project:
        gl_filters += " AND gl.project=%s"
        params.append(project)

    if frappe.db.exists("DocType", "GL Entry"):
        res = frappe.db.sql(f"""
            SELECT COALESCE(SUM(gl.debit - gl.credit), 0)
            FROM `tabGL Entry` gl
            INNER JOIN `tabAccount` acc ON gl.account = acc.name
            {gl_filters}
        """, params)
        if res and res[0][0]:
            total_expenses = float(res[0][0])

    net_margin = total_revenue - total_expenses

    cust_retention = 0.0
    subc_retention = 0.0
    if frappe.db.exists("Account", "1320 - محجوزات ضمان حسن التنفيذ للعملاء (Retention) - Rkn"):
        r = frappe.db.sql("SELECT COALESCE(SUM(debit - credit), 0) FROM `tabGL Entry` WHERE account='1320 - محجوزات ضمان حسن التنفيذ للعملاء (Retention) - Rkn' AND is_cancelled=0")
        if r and r[0][0]:
            cust_retention = float(r[0][0])
    if frappe.db.exists("Account", "2130 - محجوزات ضمان مقاولي الباطن - Rkn"):
        r = frappe.db.sql("SELECT COALESCE(SUM(credit - debit), 0) FROM `tabGL Entry` WHERE account='2130 - محجوزات ضمان مقاولي الباطن - Rkn' AND is_cancelled=0")
        if r and r[0][0]:
            subc_retention = float(r[0][0])

    vat_out = 0.0
    vat_in = 0.0
    if frappe.db.exists("Account", "2330 - ضريبة القيمة المضافة للمخرجات 15% - Rkn"):
        r = frappe.db.sql("SELECT COALESCE(SUM(credit - debit), 0) FROM `tabGL Entry` WHERE account='2330 - ضريبة القيمة المضافة للمخرجات 15% - Rkn' AND is_cancelled=0")
        if r and r[0][0]:
            vat_out = float(r[0][0])
    if frappe.db.exists("Account", "1510 - ضريبة القيمة المضافة للمدخلات 15% - Rkn"):
        r = frappe.db.sql("SELECT COALESCE(SUM(debit - credit), 0) FROM `tabGL Entry` WHERE account='1510 - ضريبة القيمة المضافة للمدخلات 15% - Rkn' AND is_cancelled=0")
        if r and r[0][0]:
            vat_in = float(r[0][0])
    net_vat_payable = vat_out - vat_in

    proj_title = f"المشروع: {project}" if project else "الشركة بالكامل (جميع المشاريع والعمليات)"

    summary_lines = [
        f"📊 الملخص المالي والتنفيذي اللحظي - {proj_title}:",
        f"🏢 الشركة: {company}",
        f"💰 إجمالي السيولة النقدية والمصرفية المتاحة: {total_liquidity:,.2f} ريال سعودي",
        f"   🔹 أرصدة الصناديق والعهد: {cash_balance:,.2f} ريال",
        f"   🔹 أرصدة الحسابات البنكية: {bank_balance:,.2f} ريال",
        f"📈 إجمالي إيرادات ومستخلصات الأعمال المعتمدة: {total_revenue:,.2f} ريال سعودي",
        f"📉 إجمالي التكاليف والمصروفات المباشرة: {total_expenses:,.2f} ريال سعودي",
        f"💵 صافي هامش الأرباح التشغيلية: {net_margin:,.2f} ريال سعودي",
        "📌 موقف محجوزات الضمان (Retention):",
        f"   🔸 محجوزات ضمان مستحقة لدى العملاء: {cust_retention:,.2f} ريال",
        f"   🔸 محجوزات ضمان محتجزة لمقاولي الباطن: {subc_retention:,.2f} ريال",
        "🏛️ الموقف الضريبي لهيئة الزكاة والضريبة والجمارك (ZATCA):",
        f"   🔹 ضريبة المخرجات (المبيعات): {vat_out:,.2f} ريال",
        f"   🔹 ضريبة المدخلات (المشتريات): {vat_in:,.2f} ريال",
        f"   ⚖️ صافي الضريبة واجبة السداد للهيئة: {net_vat_payable:,.2f} ريال سعودي"
    ]

    if project:
        proj_url = frappe.utils.get_url(f"/app/project/{project}")
        summary_lines.append("\nرابط ملف المشروع:")
        summary_lines.append(proj_url)

    clean_msg = "\n".join(summary_lines)

    return {
        "status": "success",
        "project": project,
        "company": company,
        "liquidity": total_liquidity,
        "revenue": total_revenue,
        "expenses": total_expenses,
        "net_margin": net_margin,
        "customer_retention": cust_retention,
        "subcontractor_retention": subc_retention,
        "vat_payable": net_vat_payable,
        "message": clean_msg
    }
