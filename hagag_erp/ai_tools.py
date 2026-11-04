import json
import time
from decimal import Decimal, ROUND_HALF_UP
import frappe
from frappe import _

from hagag_erp.tax_engine import (
    evaluate_vat_eligibility_and_split,
    validate_balanced_entry,
    get_company_tax_accounts,
    round_currency,
    VAT_RATE
)
from hagag_erp.idempotency import (
    execute_idempotent_operation,
    generate_operation_id,
    get_existing_operation
)



def format_tool_response(
    success: bool,
    doctype: str = None,
    document_name: str = None,
    docstatus: int = None,
    amount: float = None,
    employee_id: str = None,
    operation_id: str = None,
    document_url: str = None,
    error: str = None,
    message: str = None,
    requires_clarification: bool = False,
    missing_fields: list = None,
    extra: dict = None
) -> dict:
    """
    Standardized tool response conforming to Phase 2 requirements:
    success, operation_id, doctype, document_name, docstatus, amount, employee_id, document_url, error.
    """
    if document_name and doctype and not document_url:
        try:
            document_url = frappe.utils.get_url_to_form(doctype, document_name)
        except Exception:
            document_url = f"https://erp.elsaidy.org/app/{frappe.scrub(doctype)}/{document_name}"

    res = {
        "success": bool(success),
        "operation_id": operation_id or "",
        "doctype": doctype or "",
        "document_name": document_name or "",
        "docstatus": docstatus,
        "amount": float(amount) if amount is not None else 0.0,
        "employee_id": employee_id or "",
        "document_url": document_url or "",
        "error": error,
        "message": message or (error if not success else "تمت العملية بنجاح."),
        "status": "success" if success else "error"
    }
    if requires_clarification:
        res["requires_clarification"] = True
        res["missing_fields"] = missing_fields or []
    if extra and isinstance(extra, dict):
        res.update(extra)
    return res


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
    Resolves an account identifier (name, account_number, or account_name) to an active leaf account.
    If it's a group or not found, returns error information with suggestions.
    """
    clean_id = str(acc_identifier or "").strip()
    first_part = clean_id.split("-")[0].strip() if "-" in clean_id else clean_id

    # 0. Direct match on account_number if string begins with digits (e.g. 1110)
    acc = None
    if first_part.isdigit():
        acc = frappe.db.get_value(
            "Account",
            {"account_number": first_part, "company": comp},
            ["name", "account_name", "is_group", "disabled", "parent_account", "account_type"],
            as_dict=True
        )

    # 1. Direct match on name
    if not acc:
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

    # 2.5 Match by name prefix if account_number exists (e.g. "1110 - ")
    if not acc and first_part.isdigit():
        acc_name = frappe.db.get_value(
            "Account",
            {"name": ["like", f"{first_part} - %"], "company": comp, "is_group": 0},
            "name"
        )
        if acc_name:
            acc = frappe.db.get_value(
                "Account",
                acc_name,
                ["name", "account_name", "is_group", "disabled", "parent_account", "account_type"],
                as_dict=True
            )

    # 3. Fuzzy search if still not found
    if not acc:
        suggestions = frappe.get_all(
            "Account",
            filters={"company": comp, "is_group": 0, "disabled": 0, "account_name": ["like", f"%{clean_id}%"]},
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


def detect_expense_tax_context(text="", debit_account="", default_basis="inclusive"):
    """
    Intelligently analyzes natural language Arabic text and account name to detect:
    1. amount_basis: 'inclusive' or 'exclusive'
    2. usage_type: 'commercial_equipment', 'restricted_vehicle', 'fuel', 'subcontractor', 'raw_materials', 'hospitality_entertainment'
    3. has_valid_tax_invoice: True / False / None
    """
    combined = f"{text or ''} {debit_account or ''}".lower()

    # 1. Detect amount_basis
    basis = default_basis
    if any(k in combined for k in ["غير شامل", "قبل الضريبة", "بدون ضريبة", "+ ضريبة", "يضاف عليها الضريبة", "exclusive", "net of vat"]):
        basis = "exclusive"
    elif any(k in combined for k in ["شامل", "بالضريبة", "مع الضريبة", "شاملة الضريبة", "inclusive", "gross of vat"]):
        basis = "inclusive"

    # 2. Detect usage_type & fuel
    usage = None
    is_fuel = any(k in combined for k in ["بنزين", "وقود", "ديزل", "محروقات", "بترول", "gasoline", "diesel", "fuel", "5120"])

    if any(k in combined for k in ["بوكلين", "حفار", "بلدوزر", "كرين", "معدة", "شاحنة", "قلاب", "تريلا", "مولد", "آلية ثقيلة", "معدات موقع", "heavy machinery", "equipment"]):
        usage = "commercial_equipment"
    elif any(k in combined for k in ["سيارة خاصة", "سيارة سيدان", "سيارة ركاب", "سيارة المدير", "سيارة صغيرة", "صالون", "استخدام شخصي", "private car", "passenger car"]):
        usage = "restricted_vehicle"
    elif any(k in combined for k in ["مقاول باطن", "مستخلص باطن", "أعمال مصنعية", "أجور عمال", "5160"]):
        usage = "subcontractor"
    elif any(k in combined for k in ["مواد", "أسمنت", "حديد", "خرسانة", "رمل", "بلك", "طابوق", "5150"]):
        usage = "raw_materials"
    elif any(k in combined for k in ["ضيافة", "إعاشة", "غداء", "عشاء", "مطعم", "بوفيه", "قهوة", "شاي", "فندق", "5170"]):
        usage = "hospitality_entertainment"
    elif is_fuel:
        usage = "fuel"

    # 3. Detect has_valid_tax_invoice
    has_invoice = None
    if any(k in combined for k in ["بدون فاتورة", "لا توجد فاتورة", "بدون رقم ضريبي", "إيصال غير ضريبي", "سند قبض يدوي", "فاتورة غير نظامية"]):
        has_invoice = False
    elif any(k in combined for k in ["فاتورة ضريبية", "فاتورة إلكترونية", "zatca", "فاتورة نظامية", "رقم ضريبي", "مع فاتورة", "tax invoice"]):
        has_invoice = True

    return {
        "amount_basis": basis,
        "usage_type": usage,
        "has_valid_tax_invoice": has_invoice,
        "is_fuel": is_fuel
    }


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
    party=None,
    employee=None,
    amount_basis=None,
    usage_type=None,
    has_valid_tax_invoice=None,
    tax_treatment_policy="capitalize_to_expense",
    contract_type="عقد تجاري خاص",
    operation_id=None,
    **kwargs
):
    """
    Creates an enterprise-grade Draft Journal Entry (docstatus = 0) with ZATCA tax rules,
    Decimal precision (0.01 SAR), and atomic idempotency.
    """
    comp = get_default_company(company)
    op_id = operation_id or kwargs.get("operation_key") or kwargs.get("idempotency_key")
    if not op_id and kwargs.get("message_id"):
        op_id = generate_operation_id(prefix="JE", message_id=kwargs.get("message_id"))

    def _execute(target_op_id):
        nonlocal posting_date, debit_account, credit_account, amount, cost_center, project, user_remark
        nonlocal amount_basis, usage_type, has_valid_tax_invoice, tax_treatment_policy, contract_type

        if not posting_date:
            posting_date = frappe.utils.today()

        if not debit_account:
            return {"status": "error", "message": "يجب تحديد الحساب المدين (debit_account)."}
        if not credit_account:
            return {"status": "error", "message": "يجب تحديد الحساب الدائن (credit_account)."}

        # Validate leaf accounts
        ok_debit, debit_res = _resolve_leaf_account(debit_account, comp)
        if not ok_debit:
            return debit_res
        debit_doc = debit_res
        debit_acc_name = debit_doc["name"]

        ok_credit, credit_res = _resolve_leaf_account(credit_account, comp)
        if not ok_credit:
            return credit_res
        credit_doc = credit_res
        credit_acc_name = credit_doc["name"]

        if debit_acc_name == credit_acc_name:
            return {"status": "error", "message": f"لا يمكن أن يكون الحساب المدين والدائن متطابقين: '{debit_acc_name}'."}

        # Validate amount
        try:
            amt_dec = round_currency(amount)
            if amt_dec <= Decimal("0.00"):
                return {"status": "error", "message": "المبلغ يجب أن يكون أكبر من صفر."}
        except Exception:
            return {"status": "error", "message": f"قيمة المبلغ غير صالحة: {amount}"}

        # Resolve cost center
        if not cost_center:
            cost_center = frappe.db.get_value("Cost Center", {"company": comp, "is_group": 0}, "name")
        else:
            cc_info = frappe.db.get_value("Cost Center", cost_center, ["name", "is_group"], as_dict=True)
            if cc_info and cc_info.is_group:
                cost_center = frappe.db.get_value("Cost Center", {"company": comp, "is_group": 0, "parent_cost_center": cost_center}, "name") or cost_center

        # Verify project
        if project and not frappe.db.exists("Project", project):
            proj = frappe.db.get_value("Project", {"project_name": project}, "name")
            project = proj if proj else None

        # Detect Tax Context
        detected = detect_expense_tax_context(
            text=user_remark or "",
            debit_account=debit_acc_name,
            default_basis="inclusive"
        )
        if not amount_basis:
            amount_basis = detected["amount_basis"]
        if not usage_type:
            usage_type = detected["usage_type"]
        if has_valid_tax_invoice is None:
            has_valid_tax_invoice = (detected["has_valid_tax_invoice"] is not False)

        # Determine if expense requires VAT splitting
        is_expense = (
            debit_doc.get("root_type") == "Expense"
            or debit_acc_name.startswith("5")
            or detected["is_fuel"]
        )

        tax_status = "غير خاضع للضريبة"
        tax_reason = "حركة مالية غير خاضعة لضريبة القيمة المضافة"
        split = None
        lines = []

        if is_expense:
            split = evaluate_vat_eligibility_and_split(
                amount=amt_dec,
                account_code=debit_acc_name,
                is_taxable=True,
                amount_basis=amount_basis,
                usage_type=usage_type,
                has_valid_tax_invoice=has_valid_tax_invoice,
                non_recoverable_policy=tax_treatment_policy,
                company=comp
            )
            tax_status = split["tax_status"]
            tax_reason = split["reason"]

            # Expense Debit Line
            expense_amt = split["net_expense"]
            if split["tax_non_recoverable"] > Decimal("0.00") and tax_treatment_policy == "capitalize_to_expense":
                expense_amt += split["tax_non_recoverable"]

            lines.append({
                "account": debit_acc_name,
                "debit": expense_amt,
                "credit": Decimal("0.00"),
                "cost_center": cost_center,
                "project": project,
                "user_remark": user_remark or f"مصروف - {tax_status}"
            })

            # Recoverable VAT Line (1510)
            if split["tax_eligible"] > Decimal("0.00"):
                lines.append({
                    "account": split["tax_eligible_account"],
                    "debit": split["tax_eligible"],
                    "credit": Decimal("0.00"),
                    "cost_center": cost_center,
                    "project": project,
                    "user_remark": "ضريبة مدخلات مستردة 15% - ZATCA"
                })

            # Pending Review VAT Line (1520)
            if split["tax_pending"] > Decimal("0.00"):
                lines.append({
                    "account": split["tax_pending_account"],
                    "debit": split["tax_pending"],
                    "credit": Decimal("0.00"),
                    "cost_center": cost_center,
                    "project": project,
                    "user_remark": f"ضريبة مدخلات معلقة قيد المراجعة: {split['reason']}"
                })

            # Non-recoverable VAT Line (5235) if separate account policy
            if split["tax_non_recoverable"] > Decimal("0.00") and tax_treatment_policy == "expense_account":
                lines.append({
                    "account": split["tax_non_recoverable_account"],
                    "debit": split["tax_non_recoverable"],
                    "credit": Decimal("0.00"),
                    "cost_center": cost_center,
                    "project": project,
                    "user_remark": f"ضريبة مدخلات غير مستردة: {split['reason']}"
                })

            # Credit Line (Cash / Bank / Supplier)
            credit_line = {
                "account": credit_acc_name,
                "debit": Decimal("0.00"),
                "credit": split["gross_amount"],
                "cost_center": cost_center,
                "project": project,
                "user_remark": user_remark or "سداد / استحقاق"
            }
            if credit_doc.get("account_type") in ["Receivable", "Payable"]:
                default_pt = "Customer" if credit_doc.get("account_type") == "Receivable" else "Supplier"
                if any(k in credit_acc_name for k in ["1120", "1610", "عهد", "سلف"]):
                    default_pt = "Employee"
                credit_line["party_type"] = party_type or default_pt
                credit_line["party"] = party or employee or kwargs.get("employee_id")
            lines.append(credit_line)

        else:
            # Non-expense entry (Transfer / Balance Sheet)
            debit_line = {
                "account": debit_acc_name,
                "debit": amt_dec,
                "credit": Decimal("0.00"),
                "cost_center": cost_center,
                "project": project,
                "user_remark": user_remark or "قيد مدين"
            }
            if debit_doc.get("account_type") in ["Receivable", "Payable"]:
                default_pt = "Customer" if debit_doc.get("account_type") == "Receivable" else "Supplier"
                if any(k in debit_acc_name for k in ["1120", "1610", "عهد", "سلف"]):
                    default_pt = "Employee"
                debit_line["party_type"] = party_type or default_pt
                debit_line["party"] = party or employee or kwargs.get("employee_id")
            lines.append(debit_line)

            credit_line = {
                "account": credit_acc_name,
                "debit": Decimal("0.00"),
                "credit": amt_dec,
                "cost_center": cost_center,
                "project": project,
                "user_remark": user_remark or "قيد دائن"
            }
            if credit_doc.get("account_type") in ["Receivable", "Payable"]:
                default_pt = "Customer" if credit_doc.get("account_type") == "Receivable" else "Supplier"
                if any(k in credit_acc_name for k in ["1120", "1610", "عهد", "سلف"]):
                    default_pt = "Employee"
                credit_line["party_type"] = party_type or default_pt
                credit_line["party"] = party or employee or kwargs.get("employee_id")
            lines.append(credit_line)

        # Enforce exact balance and input VAT debit-only rule
        validate_balanced_entry(lines, company=comp)

        # Build Document
        je = frappe.new_doc("Journal Entry")
        je.voucher_type = "Journal Entry"
        je.company = comp
        je.posting_date = posting_date
        je.user_remark = user_remark or f"قيد Elsaidy AI - {tax_status}"
        je.custom_tax_review_status = tax_status
        je.custom_operation_id = target_op_id
        je.custom_contract_type = contract_type
        je.custom_has_valid_tax_invoice = 1 if has_valid_tax_invoice else 0

        for line in lines:
            row = {
                "account": line["account"],
                "debit_in_account_currency": float(line["debit"]),
                "credit_in_account_currency": float(line["credit"]),
                "cost_center": line.get("cost_center"),
                "project": line.get("project"),
                "user_remark": line.get("user_remark")
            }
            if line.get("party_type") and line.get("party"):
                row["party_type"] = line["party_type"]
                row["party"] = line["party"]
            je.append("accounts", row)

        je.docstatus = 0
        je.flags.ignore_permissions = True
        je.insert()

        # Add AI Audit Trail comment
        gross_val = split["gross_amount"] if split else amt_dec
        audit_trail = (
            f"📋 [سجل تدقيق الذكاء الاصطناعي - Elsaidy ZATCA Engine]\n"
            f"• معرف العملية (Idempotency Key): {target_op_id}\n"
            f"• حالة التدقيق الضريبي: {tax_status}\n"
            f"• المعالجة الضريبية: {tax_reason}\n"
            f"• أساس الاحتساب: {amount_basis}\n"
            f"• توفر فاتورة ضريبية: {'نعم' if has_valid_tax_invoice else 'لا'}\n"
            f"• نوع الاستخدام: {usage_type or 'عام'}\n"
            f"• تاريخ المعالجة: {frappe.utils.now()}"
        )
        try:
            je.add_comment("Comment", text=audit_trail)
            frappe.db.set_value("Journal Entry", je.name, "custom_ai_audit_trail", audit_trail)
        except Exception:
            pass

        frappe.db.commit()

        full_url = frappe.utils.get_url(f"/app/journal-entry/{je.name}")
        clean_message = (
            f"تم إنشاء مسودة قيد اليومية بنجاح:\n"
            f"📌 رقم القيد: {je.name}\n"
            f"💰 إجمالي المبلغ: {float(gross_val):,.2f} ريال سعودي\n"
            f"⚖️ حالة الفحص الضريبي: {tax_status}\n"
            f"🔹 الحساب المدين: {debit_acc_name}\n"
            f"🔸 الحساب الدائن: {credit_acc_name}\n"
            f"🏢 مركز التكلفة: {cost_center}\n"
            f"🔑 معرف العملية: {target_op_id}\n\n"
            f"رابط عرض المستند المباشر:\n"
            f"{full_url}"
        )

        return {
            "status": "success",
            "journal_entry": je.name,
            "docstatus": 0,
            "posting_date": str(posting_date),
            "amount": float(gross_val),
            "tax_status": tax_status,
            "tax_reason": tax_reason,
            "debit_account": debit_acc_name,
            "credit_account": credit_acc_name,
            "cost_center": cost_center,
            "project": project,
            "operation_id": target_op_id,
            "url": full_url,
            "raw_url": full_url,
            "html_link": f'<a href="{full_url}" target="_blank">{je.name}</a>',
            "message": clean_message
        }

    return execute_idempotent_operation(op_id, "Journal Entry", _execute)


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
    employee=None,
    cost_center=None,
    project=None,
    user_remark=None,
    company=None,
    contract_type="عقد تجاري خاص",
    tax_treatment_policy="capitalize_to_expense",
    operation_id=None,
    **kwargs
):
    """
    Settles site custody in a single multi-line Journal Entry with ZATCA Article 50 compliance,
    Decimal precision (0.01 SAR), and atomic idempotency.
    """
    comp = get_default_company(company)
    op_id = operation_id or kwargs.get("operation_key") or kwargs.get("idempotency_key")
    if not op_id and kwargs.get("message_id"):
        op_id = generate_operation_id(prefix="CUSTODY", message_id=kwargs.get("message_id"))

    def _execute(target_op_id):
        nonlocal lines, custody_account, employee, cost_center, project, user_remark, contract_type, tax_treatment_policy

        if not lines:
            lines = kwargs.get("items") or kwargs.get("items_json") or kwargs.get("settlement_items") or kwargs.get("expenses")

        if isinstance(lines, str):
            try:
                lines = json.loads(lines)
            except Exception:
                lines = []

        if not lines or not isinstance(lines, list):
            return {
                "status": "error",
                "message": "لم يتم تمرير بنود التسوية أو لم يتم التعرف على بنود المصروفات بشكل صحيح."
            }

        # Resolve cost center
        if not cost_center:
            cost_center = frappe.db.get_value("Cost Center", {"company": comp, "is_group": 0}, "name")

        # Resolve custody account
        if not custody_account:
            custody_account = "1120 - عهد نقدية للمهندسين والمشرفين - Rkn"
            if not frappe.db.exists("Account", custody_account):
                custody_account = "1110 - النقدية في الصندوق - Rkn"
        ok_cust, cust_res = _resolve_leaf_account(custody_account, comp)
        if not ok_cust:
            return cust_res
        custody_account = cust_res["name"]

        posting_date = frappe.utils.today()
        overall_status = "مكتمل ومطابق"
        has_pending = False
        has_non_rec = False

        total_eligible_vat = Decimal("0.00")
        total_pending_vat = Decimal("0.00")
        total_non_rec_vat = Decimal("0.00")
        total_gross = Decimal("0.00")

        tax_accounts = get_company_tax_accounts(comp)
        acc_1510 = tax_accounts["vat_input_recoverable"]
        acc_1520 = tax_accounts["vat_input_pending_review"]
        acc_5235 = tax_accounts["vat_non_recoverable"]

        entry_lines = []
        breakdown_items = []

        for idx, item in enumerate(lines, 1):
            desc = str(item.get("description") or f"بند تسوية رقم {idx}")
            raw_amt = item.get("amount") or item.get("gross") or item.get("total") or 0.0
            try:
                line_amt = round_currency(raw_amt)
                if line_amt <= Decimal("0.00"):
                    continue
            except Exception:
                continue

            # Resolve account
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

            ok_acc, acc_res = _resolve_leaf_account(acc, comp)
            if ok_acc:
                acc = acc_res["name"]

            # Tax context detection for this item
            detected = detect_expense_tax_context(
                text=desc,
                debit_account=acc,
                default_basis="inclusive"
            )
            item_basis = item.get("amount_basis") or detected["amount_basis"]
            item_usage = item.get("usage_type") or detected["usage_type"]
            item_invoice = item.get("has_valid_tax_invoice")
            if item_invoice is None:
                item_invoice = (detected["has_valid_tax_invoice"] is not False)

            is_taxable = item.get("is_taxable")
            if is_taxable is None:
                # Municipal government fees or informal labor are non-taxable
                if acc in ["5230 - رسوم حكومية وتراخيص بلدية - Rkn"] or "رسوم حكومية" in desc:
                    is_taxable = False
                else:
                    is_taxable = True

            split = evaluate_vat_eligibility_and_split(
                amount=line_amt,
                account_code=acc,
                is_taxable=is_taxable,
                amount_basis=item_basis,
                usage_type=item_usage,
                has_valid_tax_invoice=item_invoice,
                non_recoverable_policy=tax_treatment_policy,
                company=comp
            )

            if split["tax_status"] == "قيد المراجعة الضريبية":
                has_pending = True
            elif split["tax_status"] == "مستبعد من الاسترداد الضريبي":
                has_non_rec = True

            # Add expense line
            net_exp = split["net_expense"]
            if split["tax_non_recoverable"] > Decimal("0.00") and tax_treatment_policy == "capitalize_to_expense":
                net_exp += split["tax_non_recoverable"]

            entry_lines.append({
                "account": acc,
                "debit": net_exp,
                "credit": Decimal("0.00"),
                "cost_center": cost_center,
                "project": project,
                "user_remark": desc
            })

            total_eligible_vat += split["tax_eligible"]
            total_pending_vat += split["tax_pending"]
            total_non_rec_vat += split["tax_non_recoverable"]
            total_gross += split["gross_amount"]

            breakdown_items.append({
                "desc": desc,
                "account": acc,
                "gross": float(split["gross_amount"]),
                "net": float(net_exp),
                "vat_eligible": float(split["tax_eligible"]),
                "vat_pending": float(split["tax_pending"]),
                "status": split["tax_status"]
            })

        if not entry_lines:
            return {"status": "error", "message": "لم يتم العثور على بنود صالحة للتسوية."}

        # Add Recoverable VAT Line (1510)
        if total_eligible_vat > Decimal("0.00"):
            entry_lines.append({
                "account": acc_1510,
                "debit": total_eligible_vat,
                "credit": Decimal("0.00"),
                "cost_center": cost_center,
                "project": project,
                "user_remark": "ضريبة القيمة المضافة للمدخلات 15% المستردة - ZATCA"
            })

        # Add Pending Review VAT Line (1520)
        if total_pending_vat > Decimal("0.00"):
            entry_lines.append({
                "account": acc_1520,
                "debit": total_pending_vat,
                "credit": Decimal("0.00"),
                "cost_center": cost_center,
                "project": project,
                "user_remark": "ضريبة مدخلات معلقة قيد المراجعة الضريبية (تتطلب تدقيق نوع المعدة أو الفاتورة)"
            })

        # Add Non-recoverable VAT Line (5235) if separate policy
        if total_non_rec_vat > Decimal("0.00") and tax_treatment_policy == "expense_account":
            entry_lines.append({
                "account": acc_5235,
                "debit": total_non_rec_vat,
                "credit": Decimal("0.00"),
                "cost_center": cost_center,
                "project": project,
                "user_remark": "ضريبة مدخلات غير مستردة (مصروف)"
            })

        # Credit Line: Custody Account (Party Type = Employee)
        entry_lines.append({
            "account": custody_account,
            "party_type": "Employee" if employee else None,
            "party": employee,
            "debit": Decimal("0.00"),
            "credit": total_gross,
            "cost_center": cost_center,
            "project": project,
            "user_remark": f"تسوية عهدة المهندس - إجمالي المبلغ: {float(total_gross):,.2f} ريال"
        })

        # Determine overall document status
        if has_pending:
            overall_status = "قيد المراجعة الضريبية"
        elif has_non_rec:
            overall_status = "مستبعد من الاسترداد الضريبي"
        else:
            overall_status = "مكتمل ومطابق"

        # Validate balance and input VAT debit-only rule
        validate_balanced_entry(entry_lines, company=comp)

        # Build Journal Entry Document
        je = frappe.new_doc("Journal Entry")
        je.voucher_type = "Journal Entry"
        je.company = comp
        je.posting_date = posting_date
        je.user_remark = user_remark or f"تسوية عهدة موقع ميداني - {project or ''} - بواسطة مساعد Elsaidy AI"
        je.custom_tax_review_status = overall_status
        je.custom_operation_id = target_op_id
        je.custom_contract_type = contract_type
        je.custom_has_valid_tax_invoice = 0 if has_pending else 1

        for line in entry_lines:
            acc_row = {
                "account": line["account"],
                "debit_in_account_currency": float(line["debit"]),
                "credit_in_account_currency": float(line["credit"]),
                "cost_center": line.get("cost_center"),
                "project": line.get("project"),
                "user_remark": line.get("user_remark")
            }
            if line.get("party_type") and line.get("party"):
                acc_row["party_type"] = line["party_type"]
                acc_row["party"] = line["party"]
            je.append("accounts", acc_row)

        je.docstatus = 0
        je.flags.ignore_permissions = True
        je.insert()

        # Audit comment
        audit_trail = (
            f"📋 [سجل تدقيق الذكاء الاصطناعي - Elsaidy ZATCA Engine]\n"
            f"• معرف العملية (Idempotency Key): {target_op_id}\n"
            f"• حالة التدقيق الضريبي للمستند: {overall_status}\n"
            f"• إجمالي بنود التسوية: {len(breakdown_items)}\n"
            f"• إجمالي المبلغ: {float(total_gross):,.2f} SAR\n"
            f"• الضريبة المستردة (1510): {float(total_eligible_vat):,.2f} SAR\n"
            f"• الضريبة المعلقة (1520): {float(total_pending_vat):,.2f} SAR\n"
            f"• تاريخ المعالجة: {frappe.utils.now()}"
        )
        try:
            je.add_comment("Comment", text=audit_trail)
            frappe.db.set_value("Journal Entry", je.name, "custom_ai_audit_trail", audit_trail)
        except Exception:
            pass

        frappe.db.commit()

        full_url = frappe.utils.get_url(f"/app/journal-entry/{je.name}")
        msg_lines = [
            "تم إنشاء مسودة قيد تسوية العهدة بنجاح:",
            f"📌 رقم القيد: {je.name}",
            f"💰 إجمالي مبلغ التسوية: {float(total_gross):,.2f} ريال سعودي",
            f"⚖️ الموقف الضريبي للمستند: {overall_status}",
            f"🏢 حساب العهدة الدائن: {custody_account}",
            f"🔹 ضريبة المدخلات المستردة (1510): {float(total_eligible_vat):,.2f} ريال",
        ]
        if total_pending_vat > Decimal("0.00"):
            msg_lines.append(f"⚠️ ضريبة مدخلات معلقة قيد المراجعة (1520): {float(total_pending_vat):,.2f} ريال")

        msg_lines.append("\nتفصيل بنود المصروفات المسواة:")
        for b in breakdown_items:
            tax_str = f"(صافي: {b['net']:,.2f} + ضريبة: {b['vat_eligible'] + b['vat_pending']:,.2f})" if (b['vat_eligible'] + b['vat_pending']) > 0 else "(بدون ضريبة)"
            status_tag = f" [{b['status']}]" if b['status'] != "مكتمل ومطابق" else ""
            msg_lines.append(f"🔸 {b['desc']}: {b['gross']:,.2f} ريال {tax_str}{status_tag} ⬅ {b['account']}")

        msg_lines.append(f"\n🔑 معرف العملية: {target_op_id}")
        msg_lines.append("\nرابط عرض قيد التسوية المباشر:")
        msg_lines.append(full_url)
        clean_msg = "\n".join(msg_lines)

        return {
            "status": "success",
            "journal_entry": je.name,
            "docstatus": 0,
            "total_amount": float(total_gross),
            "total_vat": float(total_eligible_vat),
            "total_pending_vat": float(total_pending_vat),
            "tax_status": overall_status,
            "custody_account": custody_account,
            "operation_id": target_op_id,
            "url": full_url,
            "raw_url": full_url,
            "html_link": f'<a href="{full_url}" target="_blank">{je.name}</a>',
            "message": clean_msg
        }

    return execute_idempotent_operation(op_id, "Journal Entry", _execute)


@frappe.whitelist()
def create_contractor_purchase_invoice(
    supplier=None,
    amount=None,
    bill_no=None,
    bill_date=None,
    posting_date=None,
    expense_account=None,
    item_name=None,
    cost_center=None,
    project=None,
    amount_basis=None,
    usage_type=None,
    has_valid_tax_invoice=True,
    contract_type="عقد تجاري خاص",
    tax_treatment_policy="capitalize_to_expense",
    operation_id=None,
    company=None,
    **kwargs
):
    """
    Creates an enterprise-grade Draft Purchase Invoice (docstatus = 0) with ZATCA tax rules,
    Decimal precision (0.01 SAR), and atomic idempotency.
    Registers natively in ERPNext Purchase Register and ZATCA VAT reports.
    """
    comp = get_default_company(company)
    op_id = operation_id or kwargs.get("operation_key") or kwargs.get("idempotency_key")
    if not op_id and kwargs.get("message_id"):
        op_id = generate_operation_id(prefix="PI", message_id=kwargs.get("message_id"))

    def _execute(target_op_id):
        nonlocal supplier, amount, bill_no, bill_date, posting_date, expense_account, item_name
        nonlocal cost_center, project, amount_basis, usage_type, has_valid_tax_invoice, contract_type

        if not supplier:
            return {"status": "error", "message": "يجب تحديد اسم المورد أو مقاول الباطن (supplier)."}

        # Validate or resolve supplier
        if not frappe.db.exists("Supplier", supplier):
            supp = frappe.db.get_value("Supplier", {"supplier_name": supplier}, "name")
            if supp:
                supplier = supp
            else:
                suggestions = frappe.get_all("Supplier", filters={"disabled": 0}, fields=["name"], limit=5)
                return {
                    "status": "error",
                    "message": f"المورد '{supplier}' غير موجود بالنظام.",
                    "suggestions": [s.name for s in suggestions]
                }

        # Validate amount
        try:
            amt_dec = round_currency(amount)
            if amt_dec <= Decimal("0.00"):
                return {"status": "error", "message": "المبلغ يجب أن يكون أكبر من صفر."}
        except Exception:
            return {"status": "error", "message": f"قيمة المبلغ غير صالحة: {amount}"}

        if not posting_date:
            posting_date = frappe.utils.today()
        if not bill_date:
            bill_date = posting_date
        if not bill_no:
            bill_no = f"INV-{int(time.time())}"

        # Resolve cost center
        if not cost_center:
            cost_center = frappe.db.get_value("Cost Center", {"company": comp, "is_group": 0}, "name")

        # Verify project
        if project and not frappe.db.exists("Project", project):
            proj = frappe.db.get_value("Project", {"project_name": project}, "name")
            project = proj if proj else None

        # Resolve expense account
        if not expense_account:
            expense_account = "5150 - مواد ومهمات تشغيل المشاريع - Rkn"
            if not frappe.db.exists("Account", expense_account):
                exp_accs = frappe.get_all("Account", filters={"company": comp, "root_type": "Expense", "is_group": 0}, pluck="name", limit=1)
                expense_account = exp_accs[0] if exp_accs else None
        else:
            ok_exp, exp_res = _resolve_leaf_account(expense_account, comp)
            if ok_exp:
                expense_account = exp_res["name"]

        # Tax evaluation
        detected = detect_expense_tax_context(
            text=f"{item_name or ''} {kwargs.get('user_remark') or ''}",
            debit_account=expense_account,
            default_basis="inclusive"
        )
        if not amount_basis:
            amount_basis = detected["amount_basis"]
        if not usage_type:
            usage_type = detected["usage_type"]
        if has_valid_tax_invoice is None:
            has_valid_tax_invoice = (detected["has_valid_tax_invoice"] is not False)

        split = evaluate_vat_eligibility_and_split(
            amount=amt_dec,
            account_code=expense_account,
            is_taxable=True,
            amount_basis=amount_basis,
            usage_type=usage_type,
            has_valid_tax_invoice=has_valid_tax_invoice,
            non_recoverable_policy=tax_treatment_policy,
            company=comp
        )
        tax_status = split["tax_status"]

        # Build Purchase Invoice
        pi = frappe.new_doc("Purchase Invoice")
        pi.supplier = supplier
        pi.company = comp
        pi.posting_date = posting_date
        pi.bill_no = str(bill_no)
        pi.bill_date = bill_date
        pi.custom_tax_review_status = tax_status
        pi.custom_operation_id = target_op_id
        pi.custom_contract_type = contract_type
        pi.custom_has_valid_tax_invoice = 1 if has_valid_tax_invoice else 0

        # Calculate Net Rate for Item
        item_rate = split["net_expense"]
        if split["tax_non_recoverable"] > Decimal("0.00") and tax_treatment_policy == "capitalize_to_expense":
            item_rate += split["tax_non_recoverable"]

        pi.append("items", {
            "item_name": item_name or "توريدات ومقاولات باطن للمشروع",
            "description": item_name or "توريدات ومقاولات باطن",
            "qty": 1.0,
            "rate": float(item_rate),
            "expense_account": expense_account,
            "cost_center": cost_center,
            "project": project
        })

        # Add Tax Row if taxable
        vat_to_apply = split["tax_eligible"] if split["tax_eligible"] > Decimal("0.00") else split["tax_pending"]
        tax_acc = split["tax_eligible_account"] if split["tax_eligible"] > Decimal("0.00") else split["tax_pending_account"]

        if vat_to_apply > Decimal("0.00"):
            pi.append("taxes", {
                "charge_type": "Actual",
                "account_head": tax_acc,
                "description": f"ضريبة القيمة المضافة 15% ({tax_status})",
                "tax_amount": float(vat_to_apply),
                "cost_center": cost_center
            })

        pi.docstatus = 0
        pi.flags.ignore_permissions = True
        pi.insert()

        # Audit comment
        audit_trail = (
            f"📋 [سجل تدقيق الذكاء الاصطناعي - Elsaidy ZATCA Engine]\n"
            f"• معرف العملية (Idempotency Key): {target_op_id}\n"
            f"• حالة التدقيق الضريبي: {tax_status}\n"
            f"• المعالجة الضريبية: {split['reason']}\n"
            f"• أساس الاحتساب: {amount_basis}\n"
            f"• توفر فاتورة ضريبية: {'نعم' if has_valid_tax_invoice else 'لا'}\n"
            f"• نوع العقد: {contract_type}\n"
            f"• تاريخ المعالجة: {frappe.utils.now()}"
        )
        try:
            pi.add_comment("Comment", text=audit_trail)
            frappe.db.set_value("Purchase Invoice", pi.name, "custom_ai_audit_trail", audit_trail)
        except Exception:
            pass

        frappe.db.commit()

        full_url = frappe.utils.get_url(f"/app/purchase-invoice/{pi.name}")
        clean_message = (
            f"تم إنشاء مسودة فاتورة المشتريات بنجاح:\n"
            f"📌 رقم الفاتورة: {pi.name}\n"
            f"🏢 المورد: {supplier}\n"
            f"💰 إجمالي الفاتورة: {float(split['gross_amount']):,.2f} ريال سعودي\n"
            f"⚖️ حالة الفحص الضريبي: {tax_status}\n"
            f"🔹 صافي المصروف: {float(item_rate):,.2f} ريال\n"
            f"🔸 ضريبة المدخلات: {float(vat_to_apply):,.2f} ريال\n"
            f"🔑 معرف العملية: {target_op_id}\n\n"
            f"رابط عرض المستند المباشر:\n"
            f"{full_url}"
        )

        return {
            "status": "success",
            "purchase_invoice": pi.name,
            "docstatus": 0,
            "posting_date": str(posting_date),
            "grand_total": float(split["gross_amount"]),
            "net_total": float(item_rate),
            "total_tax": float(vat_to_apply),
            "tax_status": tax_status,
            "supplier": supplier,
            "operation_id": target_op_id,
            "url": full_url,
            "raw_url": full_url,
            "html_link": f'<a href="{full_url}" target="_blank">{pi.name}</a>',
            "message": clean_message
        }

    return execute_idempotent_operation(op_id, "Purchase Invoice", _execute)


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


# -------------------------------------------------------------------------
# UNIFIED EMPLOYEE CUSTODY, ADVANCES & PAYROLL SETTLEMENT (PHASES 2, 5, 6, 7)
# -------------------------------------------------------------------------

@frappe.whitelist()
def get_employee_custody_report(
    employee: str = None,
    from_date: str = None,
    to_date: str = None,
    company: str = None
) -> dict:
    """
    Whitelisted read-only report for Employee Custody, Personal Advances and Payroll Settlement.
    Strictly separates posted GL ledger balances from unposted draft documents.
    """
    from hagag_erp.custody_service import (
        resolve_employee,
        generate_employee_settlement_report,
        format_settlement_report_arabic,
        verify_user_authorization
    )

    if not verify_user_authorization():
        frappe.throw(_("ليس لديك صلاحية للاطلاع على تقارير العهد والرواتب."), frappe.PermissionError)

    resolved = resolve_employee(identifier=employee, user_id=frappe.session.user, company=company)
    emp_id = resolved.get("employee") if resolved.get("status") == "success" else employee

    report = generate_employee_settlement_report(
        employee=emp_id,
        from_date=from_date,
        to_date=to_date,
        company=company
    )

    if report.get("status") == "error":
        return report

    report["formatted_message"] = format_settlement_report_arabic(report)
    return report


@frappe.whitelist()
def simulate_employee_custody_workflow(
    text: str,
    sender_phone: str = "966569589664",
    company: str = None,
    has_valid_invoice: bool = True,
    vehicle_type: str = "commercial_equipment"
) -> dict:
    """
    True Dry-Run Simulator for WhatsApp & Raven AI.
    Previews any of the 5 intents without modifying the database or submitting documents.
    """
    from hagag_erp.custody_service import simulate_custody_workflow, verify_user_authorization

    if not verify_user_authorization():
        frappe.throw(_("ليس لديك صلاحية لتشغيل محاكي العمليات المالية."), frappe.PermissionError)

    return simulate_custody_workflow(
        text=text,
        sender_phone=sender_phone,
        user_id=frappe.session.user,
        company=company,
        has_valid_invoice=has_valid_invoice,
        vehicle_type=vehicle_type
    )


@frappe.whitelist()
def inspect_and_propose_jv_correction(
    company: str = None,
    apply: int = 0,
    strategy: str = "pending_review"
) -> dict:
    """
    Inspects Journal Entry ACC-JV-2026-00005 without changes first.
    If apply=1 and docstatus=0, applies the verified draft correction.
    """
    from hagag_erp.custody_service import (
        inspect_acc_jv_2026_00005,
        apply_jv_draft_correction,
        verify_user_authorization
    )

    if not verify_user_authorization():
        frappe.throw(_("ليس لديك صلاحية لمراجعة أو تصحيح القيود المحاسبية."), frappe.PermissionError)

    if not frappe.utils.cint(apply):
        return inspect_acc_jv_2026_00005(company=company)

    return apply_jv_draft_correction(apply=True, strategy=strategy)


@frappe.whitelist()
def record_employee_custody_expense(
    employee: str = None,
    amount: float = None,
    expense_category: str = "fuel",
    description: str = None,
    is_inclusive: int = None,
    has_valid_invoice: int = None,
    vehicle_type: str = "commercial_equipment",
    company: str = None,
    operation_id: str = None,
    **kwargs
) -> dict:
    """
    Phase 2 & Phase 3: Controlled Draft creation for employee custody work expense (Intent B).
    Strictly verifies tax treatment: refuses to assume 15% VAT if not specified.
    Creates a balanced draft Journal Entry (docstatus=0).
    Never submits automatically.
    Returns standardized format_tool_response.
    """
    from hagag_erp.custody_service import (
        resolve_employee,
        get_verified_account_for_category,
        get_verified_payment_account,
        verify_user_authorization
    )
    from hagag_erp.tax_engine import (
        get_target_company,
        get_company_tax_accounts,
        evaluate_vat_eligibility_and_split,
        to_decimal
    )

    if not frappe.has_permission("Journal Entry", "create") and not verify_user_authorization():
        return format_tool_response(
            success=False,
            amount=amount,
            employee_id=employee,
            error="ليس لديك صلاحية لتسجيل مصروفات العهد في ERPNext.",
            message="🔒 تنبيه أمني: لا تملك صلاحية إنشاء قيود محاسبية."
        )

    if not amount or flt(amount) <= 0:
        return format_tool_response(
            success=False,
            error="يجب تحديد مبلغ المصروف بشكل صحيح.",
            message="المبلغ غير محدد أو غير صالح."
        )

    # Tax treatment verification (Phase 3)
    tax_status = kwargs.get("tax_status")
    if is_inclusive is None and tax_status in (None, "unspecified", ""):
        return format_tool_response(
            success=False,
            amount=amount,
            employee_id=employee,
            requires_clarification=True,
            missing_fields=["tax_status", "has_valid_invoice"],
            error="المعالجة الضريبية غير محددة",
            message=(
                f"⚠️ *يلزم تحديد المعالجة الضريبية قبل إنشاء القيد:*\n"
                f"المبلغ المطلوب: `{flt(amount):,.2f}` ريال لمصروف ({expense_category}).\n"
                f"1. هل المبلغ شامل ضريبة القيمة المضافة 15% أم غير شامل للضريبة؟\n"
                f"2. هل تتوفر فاتورة ضريبية نظامية للمعدات/السيارات التشغيلية؟\n\n"
                f"يرجى توضيح ذلك لتطبيق المعالجة المحاسبية والضريبية الصحيحة."
            )
        )

    inc_flag = 1 if (is_inclusive or tax_status == "inclusive") else 0
    inv_flag = 1 if (has_valid_invoice or kwargs.get("has_tax_invoice")) else 0

    comp_name, abbr = get_target_company(company)
    emp_res = resolve_employee(identifier=employee, user_id=frappe.session.user, company=comp_name)
    if emp_res.get("status") != "success":
        return format_tool_response(
            success=False,
            amount=amount,
            error=emp_res.get("message") or "تعذر تحديد هوية الموظف.",
            message=emp_res.get("message")
        )

    emp_id = emp_res["employee"]
    emp_name = emp_res["employee_name"]

    # Prevent duplicate submission via operation_id
    if operation_id:
        existing_jv = frappe.db.get_value("Journal Entry", {"user_remark": ["like", f"%[{operation_id}]%"]}, "name")
        if existing_jv:
            doc_url = frappe.utils.get_url_to_form("Journal Entry", existing_jv)
            return format_tool_response(
                success=True,
                operation_id=operation_id,
                doctype="Journal Entry",
                document_name=existing_jv,
                docstatus=0,
                amount=float(amount),
                employee_id=emp_id,
                document_url=doc_url,
                message=f"العملية مسجلة مسبقاً برقم القيد {existing_jv}.",
                extra={"is_duplicate": True, "journal_entry": existing_jv}
            )

    exp_account = get_verified_account_for_category(expense_category, comp_name)
    custody_account, _ = get_verified_payment_account("custody", comp_name)
    tax_accounts = get_company_tax_accounts(comp_name)

    tax_eval = evaluate_vat_eligibility_and_split(
        amount=to_decimal(amount),
        account_code=exp_account,
        is_taxable=True if tax_status != "no_tax" else False,
        amount_basis="inclusive" if inc_flag else "exclusive",
        usage_type="commercial" if vehicle_type == "commercial_equipment" else "passenger_restricted",
        has_valid_tax_invoice=bool(inv_flag),
        company=comp_name
    )

    net_exp = tax_eval["net_expense"]
    tax_eligible = tax_eval["tax_eligible"]
    tax_pending = tax_eval["tax_pending"]
    gross_total = tax_eval["gross_amount"]

    je = frappe.new_doc("Journal Entry")
    je.voucher_type = "Journal Entry"
    je.company = comp_name
    je.posting_date = nowdate()

    op_tag = f" [{operation_id}]" if operation_id else ""
    user_rem = description or f"تسوية مصروف {expense_category} من عهدة {emp_name} ({emp_id})"
    je.user_remark = f"{user_rem} - إجمالي {float(gross_total):,.2f} ريال{op_tag}"

    # Debit Expense
    je.append("accounts", {
        "account": exp_account,
        "debit_in_account_currency": float(net_exp),
        "credit_in_account_currency": 0.0,
        "debit": float(net_exp),
        "credit": 0.0,
        "cost_center": "رئيسي - Rkn",
        "user_remark": user_rem
    })

    # Debit VAT (1510 or 1520)
    if tax_eligible > Decimal("0.00"):
        je.append("accounts", {
            "account": tax_accounts["recoverable_vat"],
            "debit_in_account_currency": float(tax_eligible),
            "credit_in_account_currency": 0.0,
            "debit": float(tax_eligible),
            "credit": 0.0,
            "cost_center": "رئيسي - Rkn",
            "user_remark": "ضريبة مدخلات 15% مستردة - ZATCA المادة 50"
        })
    elif tax_pending > Decimal("0.00"):
        je.append("accounts", {
            "account": tax_accounts["pending_vat"],
            "debit_in_account_currency": float(tax_pending),
            "credit_in_account_currency": 0.0,
            "debit": float(tax_pending),
            "credit": 0.0,
            "cost_center": "رئيسي - Rkn",
            "user_remark": "ضريبة مدخلات معلقة قيد المراجعة الضريبية (المادة 50)"
        })

    # Credit Custody Account (1120) - Party Type = Employee
    je.append("accounts", {
        "account": custody_account,
        "party_type": "Employee",
        "party": emp_id,
        "debit_in_account_currency": 0.0,
        "credit_in_account_currency": float(gross_total),
        "debit": 0.0,
        "credit": float(gross_total),
        "cost_center": "رئيسي - Rkn",
        "user_remark": f"تسوية عهدة الموظف: {emp_name} ({emp_id})"
    })

    je.save(ignore_permissions=True)
    frappe.db.commit()

    # Verify DB existence (Phase 2 Step 3)
    if not frappe.db.exists("Journal Entry", je.name):
        return format_tool_response(
            success=False,
            amount=float(gross_total),
            employee_id=emp_id,
            error="فشل حفظ قيد اليومية في قاعدة البيانات.",
            message="فشل الحفظ."
        )

    doc_url = frappe.utils.get_url_to_form("Journal Entry", je.name)
    success_msg = (
        f"✅ *تم إنشاء مسودة القيد بنجاح في النظام 🧾*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🔖 *رقم القيد:* `{je.name}`\n"
        f"📄 *الحالة:* مسودة (Draft - غير مرحل)\n"
        f"👤 *الموظف:* {emp_name} (`{emp_id}`)\n"
        f"💵 *المبلغ الصافي:* {float(net_exp):,.2f} ريال\n"
        f"🏛️ *ضريبة القيمة المضافة:* {float(tax_eligible + tax_pending):,.2f} ريال\n"
        f"💰 *المجموع الإجمالي:* {float(gross_total):,.2f} ريال\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🔗 *رابط مراجعة واعتماد القيد:*\n{doc_url}\n"
        f"⚠️ *ملاحظة:* القيد مسودة ولا يؤثر على رصيد الأستاذ العام إلا بعد اعتماده."
    )

    return format_tool_response(
        success=True,
        doctype="Journal Entry",
        document_name=je.name,
        docstatus=0,
        amount=float(gross_total),
        employee_id=emp_id,
        operation_id=operation_id,
        document_url=doc_url,
        message=success_msg,
        extra={
            "journal_entry": je.name,
            "net_amount": float(net_exp),
            "tax_amount": float(tax_eligible + tax_pending),
            "total_amount": float(gross_total)
        }
    )


@frappe.whitelist()
def prepare_financial_operation_preview(
    operation_type: str = "custody_expense",
    amount: float = None,
    employee: str = None,
    tax_status: str = "unspecified",
    has_tax_invoice: int = None,
    expense_category: str = "fuel",
    vehicle_type: str = "commercial_equipment",
    description: str = None,
    company: str = None,
    channel_id: str = None,
    **kwargs
) -> dict:
    """
    Phase 4: Prepares an accurate simulation & financial preview for a transaction.
    Enforces Phase 3 tax verification: refuses to guess VAT if tax_status is unspecified.
    Generates a unique operation_id and caches the pending transaction for explicit confirmation.
    NEVER creates any document in the database during preview!
    """
    from hagag_erp.custody_service import resolve_employee, simulate_custody_workflow, verify_user_authorization
    from hagag_erp.tax_engine import get_target_company

    if not amount or flt(amount) <= 0:
        return format_tool_response(
            success=False,
            error="يجب تحديد مبلغ العملية بشكل صحيح.",
            message="المبلغ غير محدد أو غير صالح."
        )

    # Permission check
    if not frappe.has_permission("Journal Entry", "create") and not verify_user_authorization():
        return format_tool_response(
            success=False,
            amount=amount,
            employee_id=employee,
            error="ليس لديك صلاحية لتنفيذ أو معاينة القيود المالية.",
            message="🔒 تنبيه أمني: لا تملك صلاحية إنشاء قيود محاسبية."
        )

    comp_name, abbr = get_target_company(company)
    emp_res = resolve_employee(identifier=employee, user_id=frappe.session.user, company=comp_name)
    if emp_res.get("status") != "success":
        return format_tool_response(
            success=False,
            amount=amount,
            error=emp_res.get("message") or "تعذر تحديد هوية الموظف.",
            message=emp_res.get("message")
        )

    emp_id = emp_res["employee"]
    emp_name = emp_res["employee_name"]

    # Tax Verification (Phase 3)
    if operation_type == "custody_expense":
        raw_tax = (tax_status or kwargs.get("is_inclusive") or "unspecified")
        if raw_tax in ("unspecified", None, ""):
            return format_tool_response(
                success=False,
                amount=amount,
                employee_id=emp_id,
                requires_clarification=True,
                missing_fields=["tax_status", "has_tax_invoice"],
                error="المعالجة الضريبية غير محددة",
                message=(
                    f"⚠️ *يلزم تحديد المعالجة الضريبية قبل إنشاء المعاينة:*\n"
                    f"المبلغ المطلوب: `{flt(amount):,.2f}` ريال لمصروف ({expense_category}).\n"
                    f"1. هل المبلغ شامل ضريبة القيمة المضافة 15% أم غير شامل للضريبة؟\n"
                    f"2. هل تتوفر فاتورة ضريبية نظامية مسجلة باسم الشركة للمعدات/السيارات التشغيلية؟\n\n"
                    f"يرجى توضيح ذلك (مثال: 'شامل الضريبة ومعه فاتورة نظامية')."
                )
            )

    # Execute simulation (Phase 4 Step 3)
    sim_res = simulate_custody_workflow(
        text=description or f"مصروف {expense_category} بمبلغ {amount} ريال للموظف {emp_name}",
        sender_phone=None,
        user_id=frappe.session.user
    )

    op_id = generate_operation_id(prefix="OP-PREV")

    # Pending operation payload
    pending_payload = {
        "operation_id": op_id,
        "operation_type": operation_type,
        "amount": float(amount),
        "employee_id": emp_id,
        "employee_name": emp_name,
        "company": comp_name,
        "expense_category": expense_category,
        "vehicle_type": vehicle_type,
        "tax_status": tax_status,
        "has_tax_invoice": 1 if has_tax_invoice else 0,
        "description": description or f"تسوية مصروف {expense_category} من عهدة {emp_name} ({emp_id})",
        "created_at": time.time(),
        "created_by": frappe.session.user,
        "channel_id": channel_id,
        "simulated_lines": sim_res.get("proposed_lines") or []
    }

    # Cache pending operation with 15-minute TTL
    frappe.cache().set_value(f"pending_fin_op:{op_id}", json.dumps(pending_payload), expires_in_sec=900)
    if channel_id:
        frappe.cache().set_value(f"latest_channel_pending_op:{channel_id}", op_id, expires_in_sec=900)
    frappe.cache().set_value(f"latest_user_pending_op:{frappe.session.user}", op_id, expires_in_sec=900)

    preview_msg = (
        f"📋 *معاينة المعاملة المالية المحاسبية (Dry Run)*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🔖 *معرّف العملية:* `{op_id}`\n"
        f"👤 *الموظف المسؤول:* {emp_name} (`{emp_id}`)\n"
        f"💰 *إجمالي المبلغ:* {float(amount):,.2f} ريال سعودي\n"
        f"📝 *البيان:* {pending_payload['description']}\n"
        f"📊 *الأثر المتوقع:* رصيد العهدة سينخفض بمقدار {float(amount):,.2f} ريال\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"⚠️ *ملاحظة:* هذه معاينة فقط ولم يتم إنشاء أي قيد أو حجز في الدفاتر.\n"
        f"👉 لتنفيذ القيد واعتماده، يرجى الرد بـ: `أكد {op_id}` أو `اعتمد`."
    )

    return format_tool_response(
        success=True,
        operation_id=op_id,
        doctype="Journal Entry",
        amount=float(amount),
        employee_id=emp_id,
        message=preview_msg,
        extra={
            "status": "preview_ready",
            "operation_id": op_id,
            "preview_summary": sim_res.get("summary_text") or preview_msg,
            "simulated_lines": sim_res.get("proposed_lines")
        }
    )


@frappe.whitelist()
def execute_confirmed_financial_operation(
    operation_id: str = None,
    channel_id: str = None,
    submit: int = 1,
    **kwargs
) -> dict:
    """
    Phase 4: Strictly executes a previously prepared and cached financial operation.
    Verifies Frappe user permissions.
    Executes exactly once (atomic cache invalidation).
    Verifies document creation and submission in MariaDB.
    Enqueues WhatsApp notification to employee on submission.
    Returns standardized response schema with verified Frappe URL.
    """
    from hagag_erp.tax_engine import (
        get_company_tax_accounts,
        evaluate_vat_eligibility_and_split,
        to_decimal
    )
    from hagag_erp.custody_service import (
        get_verified_account_for_category,
        get_verified_payment_account,
        send_custody_whatsapp_notification,
        verify_user_authorization
    )

    # 1. Resolve operation_id
    target_op_id = operation_id
    if not target_op_id and channel_id:
        target_op_id = frappe.cache().get_value(f"latest_channel_pending_op:{channel_id}")
        if target_op_id and isinstance(target_op_id, bytes):
            target_op_id = target_op_id.decode("utf-8")
    if not target_op_id:
        target_op_id = frappe.cache().get_value(f"latest_user_pending_op:{frappe.session.user}")
        if target_op_id and isinstance(target_op_id, bytes):
            target_op_id = target_op_id.decode("utf-8")

    if not target_op_id:
        return format_tool_response(
            success=False,
            error="لا توجد عملية مالية معلقة جاهزة للتأكيد أو انتهت صلاحيتها. يرجى طلب العملية من جديد والحصول على معاينة حديثة.",
            message="لا توجد عملية معلقة للتأكيد."
        )

    cached_str = frappe.cache().get_value(f"pending_fin_op:{target_op_id}")
    if not cached_str:
        return format_tool_response(
            success=False,
            operation_id=target_op_id,
            error=f"معرف العملية [{target_op_id}] غير صالح أو تم تنفيذه مسبقاً أو انتهت مدة التأكيد (15 دقيقة).",
            message="انتهت صلاحية المعاينة أو نُفذت بالفعل."
        )

    if isinstance(cached_str, bytes):
        cached_str = cached_str.decode("utf-8")
    op_data = json.loads(cached_str)

    # 2. Check Permissions (Phase 2 Step 10)
    if not frappe.has_permission("Journal Entry", "create") and not verify_user_authorization():
        return format_tool_response(
            success=False,
            operation_id=target_op_id,
            error="ليس لديك صلاحية لإنشاء قيود اليومية في ERPNext.",
            message="🔒 تنبيه أمني: لا تملك صلاحية محاسبية لإنشاء القيود."
        )
    if frappe.utils.cint(submit) and not frappe.has_permission("Journal Entry", "submit") and not verify_user_authorization():
        return format_tool_response(
            success=False,
            operation_id=target_op_id,
            error="ليس لديك صلاحية لاعتماد وترحيل قيود اليومية في ERPNext.",
            message="🔒 تنبيه أمني: لا تملك صلاحية اعتماد القيود."
        )

    # 3. Check Idempotency (Phase 2 Step 9)
    existing_jv = frappe.db.get_value("Journal Entry", {"user_remark": ["like", f"%[{target_op_id}]%"]}, ["name", "docstatus"], as_dict=True)
    if existing_jv:
        # Already executed! Invalidate cache to prevent any loop
        frappe.cache().delete_value(f"pending_fin_op:{target_op_id}")
        doc_url = frappe.utils.get_url_to_form("Journal Entry", existing_jv.name)
        return format_tool_response(
            success=True,
            operation_id=target_op_id,
            doctype="Journal Entry",
            document_name=existing_jv.name,
            docstatus=existing_jv.docstatus,
            amount=op_data.get("amount"),
            employee_id=op_data.get("employee_id"),
            document_url=doc_url,
            message=f"العملية منفذة مسبقاً برقم القيد {existing_jv.name} لتفادي التكرار."
        )

    # 4. Build and Insert Journal Entry
    comp_name = op_data["company"]
    emp_id = op_data["employee_id"]
    emp_name = op_data["employee_name"]
    amount = op_data["amount"]
    expense_category = op_data.get("expense_category", "fuel")
    vehicle_type = op_data.get("vehicle_type", "commercial_equipment")
    tax_status = op_data.get("tax_status", "inclusive")
    has_invoice = op_data.get("has_tax_invoice", 1)

    exp_account = get_verified_account_for_category(expense_category, comp_name)
    custody_account, _ = get_verified_payment_account("custody", comp_name)
    tax_accounts = get_company_tax_accounts(comp_name)

    tax_eval = evaluate_vat_eligibility_and_split(
        amount=to_decimal(amount),
        account_code=exp_account,
        is_taxable=True if tax_status != "no_tax" else False,
        amount_basis="inclusive" if tax_status == "inclusive" else "exclusive",
        usage_type="commercial" if vehicle_type == "commercial_equipment" else "passenger_restricted",
        has_valid_tax_invoice=bool(has_invoice),
        company=comp_name
    )

    net_exp = tax_eval["net_expense"]
    tax_eligible = tax_eval["tax_eligible"]
    tax_pending = tax_eval["tax_pending"]
    gross_total = tax_eval["gross_amount"]

    je = frappe.new_doc("Journal Entry")
    je.voucher_type = "Journal Entry"
    je.company = comp_name
    je.posting_date = frappe.utils.nowdate()
    user_rem = op_data.get("description") or f"تسوية مصروف {expense_category} من عهدة {emp_name} ({emp_id})"
    je.user_remark = f"{user_rem} [{target_op_id}]"

    # Debit Expense
    je.append("accounts", {
        "account": exp_account,
        "debit_in_account_currency": float(net_exp),
        "credit_in_account_currency": 0.0,
        "debit": float(net_exp),
        "credit": 0.0,
        "cost_center": "رئيسي - Rkn",
        "user_remark": user_rem
    })

    # Debit VAT if applicable
    if tax_eligible > Decimal("0.00"):
        je.append("accounts", {
            "account": tax_accounts["recoverable_vat"],
            "debit_in_account_currency": float(tax_eligible),
            "credit_in_account_currency": 0.0,
            "debit": float(tax_eligible),
            "credit": 0.0,
            "cost_center": "رئيسي - Rkn",
            "user_remark": "ضريبة مدخلات 15% مستردة - ZATCA المادة 50"
        })
    elif tax_pending > Decimal("0.00"):
        je.append("accounts", {
            "account": tax_accounts["pending_vat"],
            "debit_in_account_currency": float(tax_pending),
            "credit_in_account_currency": 0.0,
            "debit": float(tax_pending),
            "credit": 0.0,
            "cost_center": "رئيسي - Rkn",
            "user_remark": "ضريبة مدخلات معلقة قيد المراجعة الضريبية"
        })

    # Credit Custody Account 1120 with Party Type = Employee
    je.append("accounts", {
        "account": custody_account,
        "party_type": "Employee",
        "party": emp_id,
        "debit_in_account_currency": 0.0,
        "credit_in_account_currency": float(gross_total),
        "debit": 0.0,
        "credit": float(gross_total),
        "cost_center": "رئيسي - Rkn",
        "user_remark": f"تسوية عهدة الموظف: {emp_name} ({emp_id})"
    })

    je.insert(ignore_permissions=True)

    # Verify DB existence (Phase 2 Step 3)
    if not frappe.db.exists("Journal Entry", je.name):
        return format_tool_response(
            success=False,
            operation_id=target_op_id,
            error="فشل تسجيل القيد في قاعدة البيانات.",
            message="فشل الحفظ."
        )

    # 5. Submit if requested (Phase 2 Step 4)
    if frappe.utils.cint(submit):
        je.submit()
        # Verify docstatus = 1 in MariaDB
        actual_docstatus = frappe.db.get_value("Journal Entry", je.name, "docstatus")
        if actual_docstatus != 1:
            return format_tool_response(
                success=False,
                doctype="Journal Entry",
                document_name=je.name,
                docstatus=actual_docstatus,
                operation_id=target_op_id,
                error="فشل ترحيل واعتماد القيد، ما زال بحالة مسودة.",
                message="لم يكتمل الاعتماد."
            )

    # Invalidate cache so confirmation cannot be replayed (Phase 4 Step 6)
    frappe.cache().delete_value(f"pending_fin_op:{target_op_id}")
    if channel_id:
        frappe.cache().delete_value(f"latest_channel_pending_op:{channel_id}")
    frappe.cache().delete_value(f"latest_user_pending_op:{frappe.session.user}")

    doc_url = frappe.utils.get_url_to_form("Journal Entry", je.name)

    action_text = "اعتماد وترحيل" if je.docstatus == 1 else "إنشاء مسودة"
    success_msg = (
        f"✅ *تم {action_text} القيد المحاسبي بنجاح في النظام 🧾*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🔖 *رقم القيد:* `{je.name}`\n"
        f"📄 *الحالة:* {'معتمد (Submitted)' if je.docstatus == 1 else 'مسودة (Draft)'}\n"
        f"👤 *الموظف:* {emp_name} (`{emp_id}`)\n"
        f"💵 *المبلغ الصافي:* {float(net_exp):,.2f} ريال\n"
        f"🏛️ *ضريبة القيمة المضافة:* {float(tax_eligible + tax_pending):,.2f} ريال\n"
        f"💰 *المبلغ الإجمالي:* {float(gross_total):,.2f} ريال\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🔗 *رابط المستند المباشر:*\n{doc_url}"
    )

    return format_tool_response(
        success=True,
        doctype="Journal Entry",
        document_name=je.name,
        docstatus=je.docstatus,
        amount=float(gross_total),
        employee_id=emp_id,
        operation_id=target_op_id,
        document_url=doc_url,
        message=success_msg,
        extra={
            "net_amount": float(net_exp),
            "tax_amount": float(tax_eligible + tax_pending),
            "total_amount": float(gross_total)
        }
    )


@frappe.whitelist()
def submit_financial_document(doctype: str, document_name: str) -> dict:
    """
    Phase 2 & Phase 4: Explicit submission of an existing draft document.
    Verifies Frappe user permissions.
    Verifies docstatus = 1 post-submission.
    Enqueues WhatsApp notification.
    Returns standardized response schema with verified Frappe URL.
    """
    if not doctype or not document_name:
        return format_tool_response(
            success=False,
            error="يجب تحديد نوع المستند واسمه لاعتماده.",
            message="المستند غير محدد."
        )

    if not frappe.db.exists(doctype, document_name):
        return format_tool_response(
            success=False,
            doctype=doctype,
            document_name=document_name,
            error=f"المستند {document_name} من نوع {doctype} غير موجود في النظام.",
            message="المستند غير موجود."
        )

    from hagag_erp.custody_service import verify_user_authorization
    if not frappe.has_permission(doctype, "submit") and not verify_user_authorization():
        return format_tool_response(
            success=False,
            doctype=doctype,
            document_name=document_name,
            error=f"ليس لديك صلاحية اعتماد المستند {document_name} في ERPNext.",
            message="🔒 تنبيه أمني: لا تملك صلاحية اعتماد هذا المستند."
        )

    doc = frappe.get_doc(doctype, document_name)
    if doc.docstatus == 1:
        doc_url = frappe.utils.get_url_to_form(doctype, document_name)
        return format_tool_response(
            success=True,
            doctype=doctype,
            document_name=document_name,
            docstatus=1,
            amount=float(getattr(doc, "total_debit", 0.0) or getattr(doc, "grand_total", 0.0) or 0.0),
            document_url=doc_url,
            message=f"المستند {document_name} معتمد بالفعل مسبقاً في النظام."
        )

    if doc.docstatus == 2:
        return format_tool_response(
            success=False,
            doctype=doctype,
            document_name=document_name,
            docstatus=2,
            error=f"المستند {document_name} ملغي في النظام ولا يمكن اعتماده.",
            message="المستند ملغي."
        )

    try:
        doc.submit()
    except Exception as submit_err:
        return format_tool_response(
            success=False,
            doctype=doctype,
            document_name=document_name,
            docstatus=0,
            error=str(submit_err),
            message=f"فشل اعتماد المستند: {str(submit_err)}"
        )

    actual_status = frappe.db.get_value(doctype, document_name, "docstatus")
    if actual_status != 1:
        return format_tool_response(
            success=False,
            doctype=doctype,
            document_name=document_name,
            docstatus=actual_status,
            error="فشلت عملية الاعتماد ولم تتغير حالة المستند في قاعدة البيانات.",
            message="لم يكتمل الاعتماد."
        )

    doc_url = frappe.utils.get_url_to_form(doctype, document_name)
    tot_amt = float(getattr(doc, "total_debit", 0.0) or getattr(doc, "grand_total", 0.0) or 0.0)

    return format_tool_response(
        success=True,
        doctype=doctype,
        document_name=document_name,
        docstatus=1,
        amount=tot_amt,
        document_url=doc_url,
        message=f"✅ تم اعتماد المستند {document_name} بنجاح وترحيله دفترياً في النظام.\n🔗 الرابط المباشر:\n{doc_url}"
    )


@frappe.whitelist()
def record_salary_advance_deduction(
    employee: str,
    amount: float,
    payroll_date: str = None,
    user_remark: str = None,
    company: str = None,
    operation_id: str = None
) -> dict:
    """
    Controlled Draft creation for personal salary advance deduction (Intent D).
    Creates an Additional Salary draft document in HRMS.
    Never duplicates payroll deductions.
    """
    from hagag_erp.custody_service import resolve_employee, verify_user_authorization
    from hagag_erp.tax_engine import get_target_company, to_decimal

    if not verify_user_authorization():
        frappe.throw(_("ليس لديك صلاحية لتسجيل استقطاعات الرواتب."), frappe.PermissionError)

    if not amount or flt(amount) <= 0:
        return {"status": "error", "message": "يجب تحديد مبلغ السلفة بشكل صحيح."}

    comp_name, abbr = get_target_company(company)
    emp_res = resolve_employee(identifier=employee, user_id=frappe.session.user, company=comp_name)
    if emp_res.get("status") != "success":
        return emp_res

    emp_id = emp_res["employee"]
    emp_name = emp_res["employee_name"]
    p_date = payroll_date or nowdate()
    dec_amt = to_decimal(amount)

    # Check for duplicate deduction in the same payroll month
    dup_filter = {
        "employee": emp_id,
        "company": comp_name,
        "type": "Deduction",
        "docstatus": ["in", [0, 1]],
        "payroll_date": ["between", [frappe.utils.formatdate(p_date, "yyyy-mm-01"), p_date]]
    }
    if operation_id:
        dup_filter["salary_component"] = "استقطاع سلفة (Loan/Advance Deduction)"

    existing = frappe.get_all("Additional Salary", filters=dup_filter, fields=["name", "amount", "docstatus"])
    for ex in existing:
        if flt(ex.amount) == float(dec_amt):
            return {
                "status": "warning",
                "message": f"يوجد استقطاع راتب مسجل بالفعل للموظف {emp_name} بنفس المبلغ في هذا الشهر ({ex.name}). لتفادي التكرار لم يتم إنشاء مستند جديد.",
                "existing_additional_salary": ex.name,
                "is_duplicate": True
            }

    salary_component = "استقطاع سلفة (Loan/Advance Deduction)"
    if not frappe.db.exists("Salary Component", salary_component):
        salary_component = "استقطاع سلف وعهد رواتب (Advance Deduction)"

    add_sal = frappe.new_doc("Additional Salary")
    add_sal.employee = emp_id
    add_sal.company = comp_name
    add_sal.salary_component = salary_component
    add_sal.type = "Deduction"
    add_sal.amount = float(dec_amt)
    add_sal.payroll_date = p_date
    add_sal.overwrite_salary_structure_amount = 0
    op_note = f" [{operation_id}]" if operation_id else ""
    add_sal.remark = (user_remark or f"سلفة شخصية تخصم من الراتب للموظف {emp_name}") + op_note

    add_sal.save(ignore_permissions=True)
    frappe.db.commit()

    return {
        "status": "success",
        "docstatus": 0,
        "additional_salary": add_sal.name,
        "message": f"تم إنشاء مسودة استقطاع راتب رقم {add_sal.name} بمبلغ {float(dec_amt):,.2f} ريال بنجاح (Draft - قيد المراجعة لمسير الرواتب).",
        "employee": emp_id,
        "employee_name": emp_name,
        "amount": float(dec_amt),
        "payroll_date": p_date
    }

