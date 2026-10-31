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
