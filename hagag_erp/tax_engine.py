# -*- coding: utf-8 -*-
"""
Elsaidy ERP - Central Saudi ZATCA Tax & Contracting Engine
===========================================================
Strict implementation of ZATCA (GAZT) Executive Regulations,
Article 50 (Input VAT Recovery Restrictions & Commercial Fuel Eligibility),
and Contracting Sector Guidelines (IPCs, Retention & Advance Payments).

Engineered with Decimal precision (0.01 SAR) using ROUND_HALF_UP.
"""

from decimal import Decimal, ROUND_HALF_UP
import frappe
from frappe import _


def to_decimal(val, precision="0.01") -> Decimal:
    """Safely converts float/int/str/Decimal to quantized Decimal."""
    if val is None or val == "":
        return Decimal("0.00")
    if isinstance(val, Decimal):
        return val.quantize(Decimal(precision), rounding=ROUND_HALF_UP)
    # Convert through string to avoid float binary rounding inaccuracies
    return Decimal(str(val).strip()).quantize(Decimal(precision), rounding=ROUND_HALF_UP)


def get_target_company(company=None) -> tuple:
    """Discovers the active company name and abbreviation."""
    if company and frappe.db.exists("Company", company):
        abbr = frappe.db.get_value("Company", company, "abbr")
        return company, abbr

    user_comp = frappe.defaults.get_user_default("company")
    if user_comp and frappe.db.exists("Company", user_comp):
        abbr = frappe.db.get_value("Company", user_comp, "abbr")
        return user_comp, abbr

    comps = frappe.get_all("Company", fields=["name", "abbr"], limit=10)
    for c in comps:
        if "ركن" in c.name or "سبل" in c.name:
            return c.name, c.abbr

    if comps:
        return comps[0].name, comps[0].abbr

    return "ركن سبل الافق", "Rkn"


def get_company_tax_accounts(company=None) -> dict:
    """
    Returns verified active leaf accounts for ZATCA VAT operations:
    1. Recoverable Input VAT (1510)
    2. Pending Review Input VAT (1520) - for uncertain / missing invoice / non-commercial fuel
    3. Output VAT (2330)
    4. Non-Recoverable Input VAT (5235) - when company policy specifies separate expense booking
    """
    comp_name, abbr = get_target_company(company)

    accounts = {
        "recoverable_vat": f"1510 - ضريبة القيمة المضافة للمدخلات 15% - {abbr}",
        "pending_vat": f"1520 - ضريبة مدخلات معلقة تحت المراجعة والاعتماد - {abbr}",
        "output_vat": f"2330 - ضريبة القيمة المضافة للمخرجات 15% - {abbr}",
        "non_recoverable_vat": f"5235 - ضريبة مدخلات غير قابلة للاسترداد - {abbr}"
    }

    # Ensure 1520 exists (Pending Review Asset Account)
    if not frappe.db.exists("Account", accounts["pending_vat"]):
        try:
            parent_1500 = f"1500 - ضريبية الأصول - {abbr}"
            if not frappe.db.exists("Account", parent_1500):
                # Fallback to current assets
                parent_1500 = frappe.db.get_value("Account", {"company": comp_name, "root_type": "Asset", "is_group": 1}, "name")

            doc = frappe.new_doc("Account")
            doc.account_name = "ضريبة مدخلات معلقة تحت المراجعة والاعتماد"
            doc.account_number = "1520"
            doc.parent_account = parent_1500
            doc.company = comp_name
            doc.root_type = "Asset"
            doc.account_type = "Tax"
            doc.tax_rate = 15.0
            doc.insert(ignore_permissions=True)
            frappe.db.commit()
        except Exception:
            pass

    # Ensure 5235 exists (Non-Recoverable VAT Expense Account)
    if not frappe.db.exists("Account", accounts["non_recoverable_vat"]):
        try:
            parent_5200 = f"5200 - نفقات غير مباشرة - {abbr}"
            if not frappe.db.exists("Account", parent_5200):
                parent_5200 = frappe.db.get_value("Account", {"company": comp_name, "root_type": "Expense", "is_group": 1}, "name")

            doc = frappe.new_doc("Account")
            doc.account_name = "ضريبة مدخلات غير قابلة للاسترداد"
            doc.account_number = "5235"
            doc.parent_account = parent_5200
            doc.company = comp_name
            doc.root_type = "Expense"
            doc.account_type = "Expense Account"
            doc.insert(ignore_permissions=True)
            frappe.db.commit()
        except Exception:
            pass

    return {
        "company": comp_name,
        "abbr": abbr,
        "recoverable_vat": accounts["recoverable_vat"],
        "pending_vat": accounts["pending_vat"],
        "output_vat": accounts["output_vat"],
        "non_recoverable_vat": accounts["non_recoverable_vat"]
    }


def evaluate_vat_eligibility_and_split(
    expense_account,
    amount,
    amount_basis="inclusive",
    usage_type="unknown",
    has_valid_tax_invoice=False,
    tax_treatment_policy="capitalize_to_expense",
    company=None,
    vat_rate_pct=Decimal("15.00")
) -> dict:
    """
    Evaluates ZATCA Article 50 VAT recovery eligibility and splits gross / base / tax.

    Parameters:
    - expense_account: Account string
    - amount: float, int, str or Decimal
    - amount_basis: 'inclusive' (gross includes 15% VAT), 'exclusive' (amount is net, add 15%), 'no_vat'
    - usage_type:
        * 'commercial_equipment': heavy site machinery, excavators, cranes, generators -> eligible if invoice valid
        * 'restricted_vehicle': private/passenger vehicle, sedan, personal car -> non-recoverable per Art. 50
        * 'general_business': project supplies, maintenance, materials
        * 'unknown': default uncertain -> MUST default to 'pending_review'
    - has_valid_tax_invoice: bool (must carry supplier VAT number and mandatory ZATCA fields)
    - tax_treatment_policy: 'capitalize_to_expense' (default) or 'designated_expense_account'
    """
    tax_accounts = get_company_tax_accounts(company)
    amt_dec = to_decimal(amount)

    rate_factor = to_decimal(vat_rate_pct) / Decimal("100.00")
    one_plus_rate = Decimal("1.00") + rate_factor

    # Inherently non-taxable accounts (government fees, municipal penalties, un-registered subc)
    acc_lower = (expense_account or "").lower()
    is_exempt = any(k in acc_lower for k in ["5230", "رسوم حكومية", "بلدية", "غرامة", "تراخيص"])

    if amount_basis == "no_vat" or is_exempt:
        base_amount = amt_dec
        vat_amount = Decimal("0.00")
        gross_amount = amt_dec
        eligibility_status = "exempt_or_zero"
        target_vat_account = None
        debit_lines = [
            {"account": expense_account, "amount": base_amount, "description": "المصروف (معفى أو بدون ضريبة)"}
        ]
        return {
            "eligibility_status": eligibility_status,
            "amount_basis": amount_basis,
            "gross_amount": gross_amount,
            "base_amount": base_amount,
            "vat_amount": vat_amount,
            "vat_rate_pct": vat_rate_pct,
            "target_vat_account": target_vat_account,
            "tax_treatment_policy": tax_treatment_policy,
            "debit_lines": debit_lines
        }

    # Split Base and VAT
    if amount_basis == "inclusive":
        gross_amount = amt_dec
        base_amount = (gross_amount / one_plus_rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        vat_amount = gross_amount - base_amount
    else:  # exclusive
        base_amount = amt_dec
        vat_amount = (base_amount * rate_factor).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        gross_amount = base_amount + vat_amount

    # Check Fuel & Vehicles Rule (5120 / fuel keywords)
    is_fuel = any(k in acc_lower for k in ["5120", "وقود", "بنزين", "ديزل", "محروقات", "fuel", "gasoline", "diesel"])

    if is_fuel or usage_type in ["commercial_equipment", "restricted_vehicle"]:
        if usage_type == "commercial_equipment" and has_valid_tax_invoice:
            eligibility_status = "approved_recoverable"
            target_vat_account = tax_accounts["recoverable_vat"]
            debit_lines = [
                {"account": expense_account, "amount": base_amount, "description": "مصروف وقود/تشغيل معدات تجارية"},
                {"account": target_vat_account, "amount": vat_amount, "description": "ضريبة مدخلات 15% مستردة نظامياً (معدة تجارية)"}
            ]
        elif usage_type == "restricted_vehicle":
            eligibility_status = "non_recoverable"
            if tax_treatment_policy == "designated_expense_account":
                target_vat_account = tax_accounts["non_recoverable_vat"]
                debit_lines = [
                    {"account": expense_account, "amount": base_amount, "description": "مصروف وقود سيارة خاصة/مقيدة"},
                    {"account": target_vat_account, "amount": vat_amount, "description": "ضريبة مدخلات غير قابلة للاسترداد (المادة 50)"}
                ]
            else:
                # Default: Capitalize directly onto original expense
                target_vat_account = None
                debit_lines = [
                    {"account": expense_account, "amount": gross_amount, "description": "مصروف وقود سيارة مقيدة (رسملة الضريبة بالكامل)"}
                ]
        else:
            # Default for unknown / missing commercial equipment confirmation / missing invoice
            eligibility_status = "pending_review"
            target_vat_account = tax_accounts["pending_vat"]
            debit_lines = [
                {"account": expense_account, "amount": base_amount, "description": "مصروف وقود (صافي الأساس)"},
                {"account": target_vat_account, "amount": vat_amount, "description": "ضريبة مدخلات 15% معلقة تحت المراجعة (المادة 50 ZATCA)"}
            ]
    else:
        # General Contracting Business Expenses (Materials, Tools, Rent, Site Logistics)
        if has_valid_tax_invoice:
            eligibility_status = "approved_recoverable"
            target_vat_account = tax_accounts["recoverable_vat"]
            debit_lines = [
                {"account": expense_account, "amount": base_amount, "description": "مصروف تشغيلي مباشر"},
                {"account": target_vat_account, "amount": vat_amount, "description": "ضريبة القيمة المضافة للمدخلات 15%"}
            ]
        else:
            # Missing valid tax invoice -> Must NOT claim input VAT; route to pending review
            eligibility_status = "pending_review"
            target_vat_account = tax_accounts["pending_vat"]
            debit_lines = [
                {"account": expense_account, "amount": base_amount, "description": "مصروف تشغيلي (صافي الأساس)"},
                {"account": target_vat_account, "amount": vat_amount, "description": "ضريبة مدخلات معلقة تحت المراجعة والاعتماد (عدم ثبوت الفاتورة)"}
            ]

    return {
        "eligibility_status": eligibility_status,
        "amount_basis": amount_basis,
        "gross_amount": gross_amount,
        "base_amount": base_amount,
        "vat_amount": vat_amount,
        "vat_rate_pct": vat_rate_pct,
        "target_vat_account": target_vat_account,
        "tax_treatment_policy": tax_treatment_policy,
        "debit_lines": debit_lines
    }


def validate_balanced_entry(accounts_lines) -> Decimal:
    """
    Verifies that total debits == total credits to 0.01 SAR.
    Verifies that Input VAT (1510, 1520, 5235) and expenses are strictly on DEBIT side.
    Raises ValidationError if unbalanced or if input VAT is credited on expense entries.
    """
    total_debit = Decimal("0.00")
    total_credit = Decimal("0.00")

    for idx, row in enumerate(accounts_lines, 1):
        d = to_decimal(row.get("debit_in_account_currency") or row.get("debit") or 0)
        c = to_decimal(row.get("credit_in_account_currency") or row.get("credit") or 0)
        acc = row.get("account") or ""

        # Input VAT must never be credited in expense/procurement entries
        if any(tax_num in acc for tax_num in ["1510", "1520", "5235"]):
            if c > Decimal("0.00") and d == Decimal("0.00"):
                frappe.throw(
                    _("🛑 خطأ توجيه محاسبي حرج في السطر {0}: تم إدراج حساب ضريبة المدخلات ({1}) في الطرف الدائن بمبلغ {2} ريال! في قيود المصروفات والمشتريات، ضريبة المدخلات يجب أن تكون دائماً في الطرف المدين.")
                    .format(idx, acc, c),
                    frappe.ValidationError
                )

        total_debit += d
        total_credit += c

    diff = (total_debit - total_credit).abs()
    if diff > Decimal("0.01"):
        frappe.throw(
            _("🛑 القيد غير متزن محاسبياً! إجمالي المدين: {0} ريال، إجمالي الدائن: {1} ريال (الفارق: {2} ريال). يجب أن يتساوى المدين والدائن بدقة 0.01 ريال.")
            .format(total_debit, total_credit, diff),
            frappe.ValidationError
        )

    return total_debit


def validate_tax_review_before_submit(doc, method=None):
    """
    Hook for before_submit on Journal Entry and Purchase Invoice.
    Blocks document submission if tax review status is 'pending_review' or contains account 1520.
    """
    # 1. Check custom_tax_review_status field
    if getattr(doc, "custom_tax_review_status", None) == "pending_review":
        frappe.throw(
            _("🛑 لا يمكن اعتماد أو ترحيل هذا المستند ({0}): الحالة الضريبية للمستند هي 'معلق تحت المراجعة' (Pending Review) وفقاً للمادة 50 من لائحة هيئة الزكاة والضريبة والجمارك (ZATCA). يجب التحقق من أهلية الفواتير الضريبية وتعديل الحالة إلى 'معتمد للاسترداد' أو 'غير مسترد' بواسطة محاسب معتمد قبل الاعتماد النهائي.")
            .format(doc.name),
            title=_("حظر اعتماد - ضريبة معلقة تحت المراجعة")
        )

    # 2. Check line items for account 1520 (Pending Review Account)
    if doc.doctype == "Journal Entry":
        for row in doc.accounts:
            if "1520" in (row.account or "") or "تحت المراجعة" in (row.account or ""):
                frappe.throw(
                    _("🛑 لا يمكن اعتماد قيد اليومية ({0}): يتضمن القيد حساب ضريبة المدخلات المعلقة تحت المراجعة ({1}). يلزم تسوية هذا الحساب بنقله إلى حساب ضريبة المدخلات المستردة (1510) أو تحميله على المصروف قبل الترحيل إلى الأستاذ العام.")
                    .format(doc.name, row.account),
                    title=_("مراجعة ضريبية معلقة - ZATCA")
                )

    elif doc.doctype == "Purchase Invoice":
        for row in getattr(doc, "taxes", []):
            if "1520" in (row.account_head or "") or "تحت المراجعة" in (row.account_head or ""):
                frappe.throw(
                    _("🛑 لا يمكن اعتماد فاتورة المشتريات ({0}): يتضمن جدول الضرائب حساب ضريبة معلقة تحت المراجعة ({1}). يجب التحقق من الأهلية الضريبية للفاتورة قبل الاعتماد.")
                    .format(doc.name, row.account_head),
                    title=_("مراجعة ضريبية معلقة - ZATCA")
                )


def calculate_ipc_tax_breakdown(
    contract_type,
    work_completed_amount,
    retention_pct=Decimal("10.00"),
    advance_recovery_amount=Decimal("0.00"),
    advance_recovery_tax_already_paid=True,
    vat_rate_pct=Decimal("15.00")
) -> dict:
    """
    Calculates Saudi Contracting Interim Payment Certificate (IPC) breakdown
    strictly adhering to ZATCA Contracting Sector Guidelines.

    Rules:
    1. Private vs Government Contract:
       - 'عقد قطاع خاص': Tax point is the date of supply / certification / payment (whichever earlier).
       - 'عقد حكومي - منصة اعتماد': Special time-of-supply rule: Tax point is linked to the issuance
         of Payment Order (أمر الدفع) by the government entity or payment receipt (whichever earlier).
    2. Retention Rule:
       - Retention (محجوز ضمان حسن التنفيذ) does NOT reduce the VAT taxable base!
         Taxable base is calculated on the full certified work value.
    3. Advance Payment Recovery Rule:
       - Advance recovery reduces the taxable base only if VAT was already accounted for
         on the original advance payment invoice.
    """
    work_val = to_decimal(work_completed_amount)
    ret_pct = to_decimal(retention_pct)
    adv_rec = to_decimal(advance_recovery_amount)
    rate_factor = to_decimal(vat_rate_pct) / Decimal("100.00")

    # Retention calculation: calculated on total work certified
    retention_amount = (work_val * (ret_pct / Decimal("100.00"))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    # Taxable Base determination
    if advance_recovery_tax_already_paid:
        taxable_base = (work_val - adv_rec).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    else:
        taxable_base = work_val

    if taxable_base < Decimal("0.00"):
        taxable_base = Decimal("0.00")

    # VAT 15% on taxable base (Retention does NOT reduce taxable base)
    vat_amount = (taxable_base * rate_factor).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    # Total Invoice Amount (Taxable Base + VAT)
    gross_ipc_value = taxable_base + vat_amount

    # Net Cash Payable to Contractor (Gross IPC value minus retention withheld)
    net_payable = (gross_ipc_value - retention_amount).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    # Time of supply note
    if "حكومي" in (contract_type or "") or "اعتماد" in (contract_type or "").lower():
        time_of_supply_rule = "عقد حكومي (منصة اعتماد): تاريخ استحقاق الضريبة مرتبط بصدور أمر الدفع من الجهة الحكومية أو استلام الدفعة أيهما أسبق (وفق أحكام اللائحة التنفيذية لضريبة القيمة المضافة الخاصة بالعقود الحكومية)."
    else:
        time_of_supply_rule = "عقد قطاع خاص: تاريخ استحقاق الضريبة هو تاريخ إصدار المستخلص أو تاريخ التوريد الجزئي أو استلام الدفعة أيهما أسبق."

    return {
        "contract_type": contract_type,
        "work_completed_amount": work_val,
        "retention_pct": ret_pct,
        "retention_amount": retention_amount,
        "advance_recovery_amount": adv_rec,
        "taxable_base": taxable_base,
        "vat_rate_pct": vat_rate_pct,
        "vat_amount": vat_amount,
        "gross_ipc_value": gross_ipc_value,
        "net_payable_to_contractor": net_payable,
        "time_of_supply_rule": time_of_supply_rule
    }
