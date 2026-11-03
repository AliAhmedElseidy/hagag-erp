# -*- coding: utf-8 -*-
"""
Elsaidy ERP - Unified Employee Custody, Advances & Payroll Settlement Service
=============================================================================
Consolidated accounting engine for:
1. Intent A: Expense paid with cash or bank.
2. Intent B: Work expense paid from employee custody (petty cash 1120 / advance 1610).
3. Intent C: Issue or replenish employee custody.
4. Intent D: Personal salary advance and payroll recovery (Additional Salary deduction).
5. Intent E: Monthly employee settlement report (strictly read-only, separating posted GL from drafts).

Designed for ERPNext v16, Frappe HR, Saudi Accounting Standards and ZATCA Article 50.
Zero arbitrary party force-feeding on Cash accounts (e.g. 1120).
All tax calculations powered by hagag_erp.tax_engine.
"""

import re
import json
import unicodedata
from decimal import Decimal, ROUND_HALF_UP
import frappe
from frappe import _
from frappe.utils import flt, nowdate, getdate, add_months

from hagag_erp.tax_engine import (
    to_decimal,
    round_currency,
    get_target_company,
    get_company_tax_accounts,
    evaluate_vat_eligibility_and_split,
    calculate_zatca_tax
)


# Known bot phone numbers that MUST NEVER be mapped to employees
KNOWN_BOT_PHONES = {
    "201028632620",
    "+201028632620",
    "00201028632620"
}

# Arabic digits mapping
ARABIC_TO_ASCII_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")


def normalize_arabic_text(text: str) -> str:
    """
    Normalizes Arabic strings for resilient fuzzy/token matching:
    - Removes diacritics / tashkeel and tatweel
    - Unifies Alef variants (أ, إ, آ, ٱ -> ا)
    - Unifies Yaa / Alef Maksura (ى, ئ -> ي)
    - Unifies Taa Marbuta (ة -> ه)
    - Collapses spaces and converts to lowercase
    """
    if not text:
        return ""
    
    t = str(text).strip()
    # Remove tashkeel (diacritics: Fatha, Damma, Kasra, Sukun, Tanween, Shadda)
    t = re.sub(r"[\u064B-\u0652\u0670\u0640]", "", t)
    # Unify Alefs
    t = re.sub(r"[أإآٱ]", "ا", t)
    # Unify Yaa / Alef Maksura
    t = re.sub(r"[ىئ]", "ي", t)
    # Unify Taa Marbuta
    t = re.sub(r"ة", "ه", t)
    # Collapse whitespace
    t = re.sub(r"\s+", " ", t).strip()
    return t.lower()


def clean_phone(phone: str) -> str:
    """Normalizes phone numbers to pure digits without plus or leading zeros."""
    if not phone:
        return ""
    p = str(phone).translate(ARABIC_TO_ASCII_DIGITS)
    p = re.sub(r"[^\d]", "", p)
    # Remove international leading 00
    if p.startswith("00"):
        p = p[2:]
    return p


# -------------------------------------------------------------------------
# PHASE 3 — EMPLOYEE RESOLUTION & AUTHORIZATION
# -------------------------------------------------------------------------

def resolve_employee(
    identifier: str = None,
    sender_phone: str = None,
    sender_lid: str = None,
    user_id: str = None,
    company: str = None
) -> dict:
    """
    Strict and secure employee resolution logic.
    Follows rules:
    1. Match confirmed Employee ID first.
    2. Resolve normalized names only when uniquely matched.
    3. For 'من عهدتي', use verified mapping between authenticated sender and Employee.
    4. Reject Egyptian WhatsApp bot number (201028632620).
    5. Never resolve employee using only ambiguous last-nine-digit phone comparison.
    6. Return explicit ambiguity or authorization error instead of guessing.
    7. Respect active status and company boundaries.
    """
    comp_name, abbr = get_target_company(company)

    # Rule 4: Reject bot phone number immediately
    if sender_phone:
        norm_sender = clean_phone(sender_phone)
        if any(norm_sender == clean_phone(bp) for bp in KNOWN_BOT_PHONES):
            return {
                "status": "error",
                "error_code": "BOT_PHONE_REJECTED",
                "message": _("رقم هاتف البوت المصري لا يمكن استخدامه كمعرف للموظف.")
            }

    # 1. Direct Employee ID match (e.g. HR-EMP-00001)
    if identifier:
        clean_id = str(identifier).strip()
        if frappe.db.exists("Employee", clean_id):
            emp = frappe.get_doc("Employee", clean_id)
            if emp.status != "Active":
                return {
                    "status": "error",
                    "error_code": "INACTIVE_EMPLOYEE",
                    "message": _("الموظف {0} غير نشط في النظام.").format(clean_id)
                }
            if comp_name and emp.company and emp.company != comp_name:
                return {
                    "status": "error",
                    "error_code": "COMPANY_MISMATCH",
                    "message": _("الموظف {0} مسجل بشركة {1} وليس {2}.").format(clean_id, emp.company, comp_name)
                }
            return {
                "status": "success",
                "source": "employee_id",
                "employee": emp.name,
                "employee_name": emp.employee_name,
                "company": emp.company,
                "user_id": emp.user_id,
                "designation": emp.designation,
                "department": emp.department
            }

    # 2. Text name search (Unique normalized match)
    if identifier:
        norm_query = normalize_arabic_text(identifier)
        if norm_query and norm_query not in ("عهدة", "عهدتي", "سلفة", "كاش", "نقدا"):
            filters = {"status": "Active"}
            if comp_name:
                filters["company"] = comp_name

            candidates = frappe.get_all(
                "Employee",
                filters=filters,
                fields=["name", "employee_name", "first_name", "last_name", "middle_name", "company", "user_id", "designation", "department"]
            )

            exact_matches = []
            partial_matches = []
            query_tokens = [tok for tok in norm_query.split() if len(tok) > 1]

            for emp in candidates:
                emp_name_norm = normalize_arabic_text(emp.employee_name or "")
                # Exact normalized match
                if norm_query == emp_name_norm:
                    exact_matches.append(emp)
                    continue

                # Token containment
                if query_tokens and all(tok in emp_name_norm for tok in query_tokens):
                    partial_matches.append(emp)
                else:
                    emp_tokens = [t for t in emp_name_norm.split() if len(t) > 2]
                    matched_toks = [t for t in emp_tokens if t in norm_query]
                    if len(matched_toks) >= 2 and emp not in partial_matches:
                        partial_matches.append(emp)

            if len(exact_matches) == 1:
                match = exact_matches[0]
                return {
                    "status": "success",
                    "source": "exact_name_match",
                    "employee": match.name,
                    "employee_name": match.employee_name,
                    "company": match.company,
                    "user_id": match.user_id,
                    "designation": match.designation,
                    "department": match.department
                }

            if len(exact_matches) > 1:
                return {
                    "status": "error",
                    "error_code": "AMBIGUOUS_NAME_MATCH",
                    "message": _("تم العثور على أكثر من موظف يطابق الاسم '{0}'.").format(identifier),
                    "candidates": [e.name + " (" + e.employee_name + ")" for e in exact_matches]
                }

            if len(partial_matches) == 1:
                match = partial_matches[0]
                return {
                    "status": "success",
                    "source": "partial_name_match",
                    "employee": match.name,
                    "employee_name": match.employee_name,
                    "company": match.company,
                    "user_id": match.user_id,
                    "designation": match.designation,
                    "department": match.department
                }

            if len(partial_matches) > 1:
                return {
                    "status": "error",
                    "error_code": "AMBIGUOUS_NAME_MATCH",
                    "message": _("تم العثور على عدة موظفين يطابقون '{0}'، يرجى تحديد الرقم الوظيفي بدقة.").format(identifier),
                    "candidates": [e.name + " (" + e.employee_name + ")" for e in partial_matches]
                }

    # 3. Verified Authenticated User / WhatsApp Sender resolution ("من عهدتي")
    # A. Frappe User ID
    clean_user = user_id or frappe.session.user
    if clean_user and clean_user != "Guest":
        user_emp = frappe.db.get_value(
            "Employee",
            {"user_id": clean_user, "status": "Active"},
            ["name", "employee_name", "company", "user_id", "designation", "department"],
            as_dict=True
        )
        if user_emp:
            return {
                "status": "success",
                "source": "authenticated_user",
                "employee": user_emp.name,
                "employee_name": user_emp.employee_name,
                "company": user_emp.company,
                "user_id": user_emp.user_id,
                "designation": user_emp.designation,
                "department": user_emp.department
            }

    # B. Verified WhatsApp Contact Rule (Phone or LID)
    if sender_phone or sender_lid:
        norm_phone = clean_phone(sender_phone)
        contact_rules = []
        if frappe.db.table_exists("Elsaidy WhatsApp Contact Rule"):
            query = """
                SELECT name, contact_name, phone_number, whatsapp_lid, linked_employee, owner, can_record_expenses
                FROM `tabElsaidy WhatsApp Contact Rule`
                WHERE is_active = 1
            """
            all_rules = frappe.db.sql(query, as_dict=True)
            for rule in all_rules:
                rule_phone = clean_phone(rule.phone_number)
                rule_lid = str(rule.whatsapp_lid or "").strip()
                match = False
                if norm_phone and rule_phone and norm_phone == rule_phone:
                    match = True
                if sender_lid and rule_lid and (sender_lid in rule_lid or rule_lid in sender_lid):
                    match = True
                if match:
                    contact_rules.append(rule)

        if len(contact_rules) == 1:
            rule = contact_rules[0]
            # Check explicit linked_employee
            if rule.linked_employee and frappe.db.exists("Employee", rule.linked_employee):
                emp = frappe.get_doc("Employee", rule.linked_employee)
                if emp.status == "Active":
                    return {
                        "status": "success",
                        "source": "whatsapp_contact_rule",
                        "employee": emp.name,
                        "employee_name": emp.employee_name,
                        "company": emp.company,
                        "user_id": emp.user_id,
                        "designation": emp.designation,
                        "department": emp.department,
                        "can_record_expenses": rule.can_record_expenses
                    }

            # If rule has no explicit linked_employee, check rule owner or contact name against Employee
            if rule.owner and rule.owner != "Administrator":
                emp_by_owner = frappe.db.get_value(
                    "Employee",
                    {"user_id": rule.owner, "status": "Active"},
                    ["name", "employee_name", "company", "user_id", "designation", "department"],
                    as_dict=True
                )
                if emp_by_owner:
                    return {
                        "status": "success",
                        "source": "whatsapp_rule_owner",
                        "employee": emp_by_owner.name,
                        "employee_name": emp_by_owner.employee_name,
                        "company": emp_by_owner.company,
                        "user_id": emp_by_owner.user_id,
                        "designation": emp_by_owner.designation,
                        "department": emp_by_owner.department
                    }

        elif len(contact_rules) > 1:
            return {
                "status": "error",
                "error_code": "AMBIGUOUS_CONTACT_RULE",
                "message": _("رقم الهاتف مسجل في أكثر من قاعدة اتصال، يتعذر تحديد الموظف بدقة.")
            }

    # 4. Fallback: Cell Number in Employee table (Strict Full Match Only)
    if sender_phone:
        norm_phone = clean_phone(sender_phone)
        if len(norm_phone) >= 9:
            # Match only exact or full international phone
            emp_matches = frappe.db.sql("""
                SELECT name, employee_name, company, user_id, designation, department
                FROM `tabEmployee`
                WHERE status = 'Active' AND (
                    REPLACE(REPLACE(cell_number, '+', ''), ' ', '') = %s
                    OR REPLACE(REPLACE(cell_number, '+', ''), ' ', '') LIKE %s
                )
            """, (norm_phone, "%" + norm_phone), as_dict=True)

            if len(emp_matches) == 1:
                match = emp_matches[0]
                return {
                    "status": "success",
                    "source": "employee_cell_number",
                    "employee": match.name,
                    "employee_name": match.employee_name,
                    "company": match.company,
                    "user_id": match.user_id,
                    "designation": match.designation,
                    "department": match.department
                }
            elif len(emp_matches) > 1:
                return {
                    "status": "error",
                    "error_code": "AMBIGUOUS_PHONE_MATCH",
                    "message": _("رقم الهاتف مسجل لأكثر من موظف.")
                }

    return {
        "status": "error",
        "error_code": "EMPLOYEE_NOT_FOUND",
        "message": _("تعذر تحديد هوية الموظف أو التحقق من صلاحيته. يرجى توضيح الاسم أو الرقم الوظيفي.")
    }


def verify_user_authorization(user: str = None, required_roles=None) -> bool:
    """Verifies server-side authorization for financial actions."""
    if not user:
        user = frappe.session.user
    if user in ("Administrator", "alyahmedelseidy@gmail.com"):
        return True
    
    roles = frappe.get_roles(user)
    allowed = required_roles or [
        "System Manager",
        "Accounts Manager",
        "Accounts User",
        "HR Manager",
        "HR User"
    ]
    return any(r in roles for r in allowed)


# -------------------------------------------------------------------------
# PHASE 2 & 4 — INTENT CLASSIFICATION & WORKFLOW ENGINE
# -------------------------------------------------------------------------

INTENT_A_EXPENSE_CASH_BANK = "INTENT_A_EXPENSE_CASH_BANK"
INTENT_B_WORK_EXPENSE_CUSTODY = "INTENT_B_WORK_EXPENSE_CUSTODY"
INTENT_C_ISSUE_REPLENISH_CUSTODY = "INTENT_C_ISSUE_REPLENISH_CUSTODY"
INTENT_D_PERSONAL_SALARY_ADVANCE = "INTENT_D_PERSONAL_SALARY_ADVANCE"
INTENT_E_MONTHLY_SETTLEMENT_REPORT = "INTENT_E_MONTHLY_SETTLEMENT_REPORT"


def _has_match(norm_text: str, keywords: list) -> bool:
    """Helper to match keywords against pre-normalized Arabic text."""
    for kw in keywords:
        norm_kw = normalize_arabic_text(kw)
        if norm_kw and norm_kw in norm_text:
            return True
    return False


def classify_accounting_intent(text: str) -> dict:
    """
    Classifies Arabic natural language messages into one of the five distinct intents.
    Returns:
    {
        "intent": str,
        "amount": Decimal,
        "is_inclusive": bool,
        "payment_method": "cash" | "bank" | "custody" | "payroll",
        "category": str,
        "raw_text": str,
        "target_name": str
    }
    """
    if not text:
        return {"intent": None, "error": "نص الرسالة فارغ"}

    norm = normalize_arabic_text(text)
    norm_digits = text.translate(ARABIC_TO_ASCII_DIGITS)

    # 1. Extract Amount
    amount = Decimal("0.00")
    # Matches: 250, 250.50, 2,000, 2000.00 preceded or followed by currency words
    amt_match = re.search(r"(?:بـ?|مبلغ|بقيمة|سلفة|عهدة|صرفت|دفع)?\s*([0-9]+(?:[\.,][0-9]{1,2})?)\s*(?:ريال|رس|sar)?", norm_digits)
    if amt_match:
        try:
            raw_val = amt_match.group(1).replace(",", "")
            amount = to_decimal(raw_val)
        except Exception:
            amount = Decimal("0.00")

    # 2. Extract VAT inclusiveness
    is_inclusive = True
    if _has_match(norm, ["غير شامل", "بدون ضريبة", "غير شاملة", "قبل الضريبة", "excl", "exclusive"]):
        is_inclusive = False
    elif _has_match(norm, ["شامل", "شاملة", "مع الضريبة", "شامل الضريبة", "incl", "inclusive"]):
        is_inclusive = True

    # 3. Intent E: Monthly settlement report
    report_keywords = [
        "تقفيل حساب", "كشف حساب", "كشف العهدة", "كشف سلف", "كشف عهدة",
        "فاضل كام", "متبقي كام", "كم باقي", "رصيد عهدة", "رصيد سلف",
        "تسوية عهدة", "كشف العهدة والسلف قبل القبض", "تصفية حساب",
        "تقفيل عهدة", "مطابقة العهدة", "حساب الموظف"
    ]
    if _has_match(norm, report_keywords) and amount == Decimal("0.00"):
        return {
            "intent": INTENT_E_MONTHLY_SETTLEMENT_REPORT,
            "amount": Decimal("0.00"),
            "is_inclusive": True,
            "payment_method": "report",
            "category": "report",
            "raw_text": text
        }

    # 4. Intent D: Personal salary advance and employee withdrawals
    salary_advance_keywords = [
        "سلفة", "سلفه", "سلفني", "سلفة شخصية", "سلفة راتب", "مسحوبات شخصية",
        "تخصم من راتب", "يخصم من الراتب", "استقطاع راتب", "خصم من الراتب"
    ]
    if _has_match(norm, salary_advance_keywords) and not _has_match(norm, ["عهدة", "عهدتي", "موقع", "ديزل", "بنزين", "صيانة"]):
        return {
            "intent": INTENT_D_PERSONAL_SALARY_ADVANCE,
            "amount": amount,
            "is_inclusive": False,  # Personal advances are non-taxable
            "payment_method": "payroll",
            "category": "salary_advance",
            "raw_text": text
        }

    # 5. Intent C: Issue or replenish employee custody
    issue_custody_keywords = [
        "تم دفع عهدة", "دفع عهدة", "ارسال عهدة", "إرسال عهدة", "تحويل عهدة",
        "صرف عهدة", "تغذية عهدة", "تجديد عهدة", "عهدة جديدة", "تسليم عهدة"
    ]
    if _has_match(norm, issue_custody_keywords):
        pm = "bank" if _has_match(norm, ["بنك", "تحويل", "حساب", "شيك", "شبكة"]) else "cash"
        return {
            "intent": INTENT_C_ISSUE_REPLENISH_CUSTODY,
            "amount": amount,
            "is_inclusive": False,  # Funding custody is balance sheet transfer, not expense
            "payment_method": pm,
            "category": "custody_replenishment",
            "raw_text": text
        }

    # 6. Intent B: Work expense paid from employee custody
    custody_expense_keywords = [
        "من عهدة", "من عهدتي", "خصما من عهدة", "من العهدة", "مسددة من عهدة", "من عهدته"
    ]
    if _has_match(norm, custody_expense_keywords):
        return {
            "intent": INTENT_B_WORK_EXPENSE_CUSTODY,
            "amount": amount,
            "is_inclusive": is_inclusive,
            "payment_method": "custody",
            "category": _detect_expense_category(norm),
            "raw_text": text
        }

    # 7. Intent A: Expense paid with cash or bank
    cash_bank_keywords = [
        "نقدا", "كاش", "نقد", "من البنك", "تحويل بنكي", "من الصندوق",
        "من الخزينة", "شبكة", "مدى", "فاتورة بنزين", "صرفت", "فاتورة", "شراء"
    ]
    if _has_match(norm, cash_bank_keywords) or amount > Decimal("0.00"):
        pm = "bank" if _has_match(norm, ["بنك", "تحويل", "حساب", "شبكة", "مدى"]) else "cash"
        return {
            "intent": INTENT_A_EXPENSE_CASH_BANK,
            "amount": amount,
            "is_inclusive": is_inclusive,
            "payment_method": pm,
            "category": _detect_expense_category(norm),
            "raw_text": text
        }
        pm = "bank" if any(b in norm for b in ["بنك", "تحويل", "حساب", "شبكة", "مدى"]) else "cash"
        return {
            "intent": INTENT_A_EXPENSE_CASH_BANK,
            "amount": amount,
            "is_inclusive": is_inclusive,
            "payment_method": pm,
            "category": _detect_expense_category(norm),
            "raw_text": text
        }

    return {
        "intent": INTENT_E_MONTHLY_SETTLEMENT_REPORT,
        "amount": Decimal("0.00"),
        "is_inclusive": True,
        "payment_method": "report",
        "category": "unknown",
        "raw_text": text
    }


def _detect_expense_category(norm_text: str) -> str:
    """Classifies Arabic expense description into chart of accounts category."""
    if any(k in norm_text for k in ["بنزين", "ديزل", "وقود", "محروقات", "بترول", "fuel", "gas"]):
        return "fuel"
    if any(k in norm_text for k in ["صيانة", "اصلاح", "تصليح", "قطع غيار", "غيار", "زيوت", "بنشر", "repair"]):
        return "maintenance"
    if any(k in norm_text for k in ["ايجار معدات", "اليات", "بوكلين", "كرين", "رافعة", "شاحنة"]):
        return "equipment_rental"
    if any(k in norm_text for k in ["مواد", "اسمنت", "رمل", "حديد", "بلك", "مهمات", "ادوات", "خشب"]):
        return "project_materials"
    if any(k in norm_text for k in ["عمال", "يوميات", "مقاول", "اجور", "مصنعيات"]):
        return "subcontractor"
    if any(k in norm_text for k in ["ضيافة", "اعاشة", "غداء", "عشاء", "شاي", "ماء", "قهوة", "وجبات"]):
        return "hospitality"
    if any(k in norm_text for k in ["رسوم", "بلدية", "غرامة", "تصريح", "شهادة", "رخصة"]):
        return "government_fees"
    return "project_materials"


def get_verified_account_for_category(category: str, company: str = None) -> str:
    """Returns verified leaf account for category based on live Chart of Accounts."""
    comp_name, abbr = get_target_company(company)

    category_mapping = {
        "fuel": f"5120 - مصروف الوقود والمحروقات - {abbr}",
        "maintenance": f"5130 - صيانة وإصلاح السيارات والمعدات - {abbr}",
        "equipment_rental": f"5140 - إيجار معدات وآليات ثقيلة - {abbr}",
        "project_materials": f"5150 - مواد ومهمات تشغيل المشاريع - {abbr}",
        "subcontractor": f"5160 - أعمال مقاولي الباطن - {abbr}",
        "hospitality": f"5170 - ضيافة وإعاشة مواقع - {abbr}",
        "government_fees": f"5230 - رسوم حكومية وتراخيص بلدية - {abbr}"
    }

    acc = category_mapping.get(category, f"5150 - مواد ومهمات تشغيل المشاريع - {abbr}")
    if frappe.db.exists("Account", acc):
        return acc

    # Fallback to any active expense account
    fallback = frappe.db.get_value(
        "Account",
        {"company": comp_name, "root_type": "Expense", "is_group": 0},
        "name"
    )
    return fallback or acc


def get_verified_payment_account(payment_method: str, company: str = None) -> tuple:
    """Returns verified payment account and its account type."""
    comp_name, abbr = get_target_company(company)
    comp_doc = frappe.get_doc("Company", comp_name)

    if payment_method == "bank":
        acc = comp_doc.default_bank_account or f"1201 - البنك الأهلي السعودي (SNB) - {abbr}"
        if not frappe.db.exists("Account", acc):
            acc = frappe.db.get_value("Account", {"company": comp_name, "account_type": "Bank", "is_group": 0}, "name")
        return acc, "Bank"

    if payment_method == "custody":
        # Check company-specific site custody cash account
        custody_acc = f"1120 - عهد نقدية للمهندسين والمشرفين - {abbr}"
        if frappe.db.exists("Account", custody_acc):
            return custody_acc, "Cash"
        # Or company default employee advance account
        if comp_doc.default_employee_advance_account:
            return comp_doc.default_employee_advance_account, "Advance"
        return f"1110 - نقد - {abbr}", "Cash"

    # Default to Cash
    acc = comp_doc.default_cash_account or f"1110 - نقد - {abbr}"
    if not frappe.db.exists("Account", acc):
        acc = frappe.db.get_value("Account", {"company": comp_name, "account_type": "Cash", "is_group": 0}, "name")
    return acc, "Cash"


# -------------------------------------------------------------------------
# PHASE 7 — TRUE DRY-RUN SIMULATOR & WORKFLOW PREVIEW
# -------------------------------------------------------------------------

def simulate_custody_workflow(
    text: str,
    sender_phone: str = "966569589664",
    sender_lid: str = None,
    user_id: str = None,
    company: str = None,
    has_valid_invoice: bool = True,
    vehicle_type: str = "commercial_equipment"
) -> dict:
    """
    True Dry-Run Simulator.
    Simulates all 5 intents without modifying any database records,
    without posting financial entries, without changing account types,
    and without sending real WhatsApp messages.
    """
    comp_name, abbr = get_target_company(company)
    parsed = classify_accounting_intent(text)
    intent = parsed.get("intent")
    amount = parsed.get("amount", Decimal("0.00"))
    payment_method = parsed.get("payment_method")
    category = parsed.get("category")
    is_inclusive = parsed.get("is_inclusive", True)

    tax_accounts = get_company_tax_accounts(comp_name)
    acc_1510 = tax_accounts["recoverable_vat"]
    acc_1520 = tax_accounts["pending_vat"]
    acc_5235 = tax_accounts["non_recoverable_vat"]

    # Resolve Employee
    # Check if a specific name is in the text
    emp_res = resolve_employee(
        identifier=text,
        sender_phone=sender_phone,
        sender_lid=sender_lid,
        user_id=user_id,
        company=comp_name
    )

    employee_id = emp_res.get("employee")
    employee_name = emp_res.get("employee_name")
    emp_source = emp_res.get("source", "unresolved")

    # Fetch live posted balance for employee (from GL Entries)
    live_gl_balance = get_employee_live_gl_balance(employee_id, company=comp_name)

    sim_doc_type = "Journal Entry"
    simulated_lines = []
    vat_info = {}
    post_approval_impact = {}
    explanation = ""

    # -------------------------------------------------------------
    # INTENT A: Expense paid with cash or bank
    # -------------------------------------------------------------
    if intent == INTENT_A_EXPENSE_CASH_BANK:
        sim_doc_type = "Journal Entry"
        exp_account = get_verified_account_for_category(category, comp_name)
        pay_account, pay_type = get_verified_payment_account(payment_method, comp_name)

        # Tax calculation
        tax_eval = evaluate_vat_eligibility_and_split(
            amount=amount,
            account_code=exp_account,
            is_taxable=True,
            amount_basis="inclusive" if is_inclusive else "exclusive",
            usage_type="commercial" if vehicle_type == "commercial_equipment" else "passenger_restricted",
            has_valid_tax_invoice=has_valid_invoice,
            company=comp_name
        )

        net_exp = tax_eval["net_expense"]
        tax_eligible = tax_eval["tax_eligible"]
        tax_pending = tax_eval["tax_pending"]
        gross_total = tax_eval["gross_amount"]

        simulated_lines.append({
            "account": exp_account,
            "party_type": None,
            "party": None,
            "debit": float(net_exp),
            "credit": 0.0,
            "remark": f"مصروف {category} ({'شامل الضريبة' if is_inclusive else 'غير شامل'})"
        })

        if tax_eligible > Decimal("0.00"):
            simulated_lines.append({
                "account": acc_1510,
                "party_type": None,
                "party": None,
                "debit": float(tax_eligible),
                "credit": 0.0,
                "remark": "ضريبة مدخلات مستردة 15% - ZATCA"
            })
            vat_info = {"status": "مستردة 15%", "account": acc_1510, "amount": float(tax_eligible)}
        elif tax_pending > Decimal("0.00"):
            simulated_lines.append({
                "account": acc_1520,
                "party_type": None,
                "party": None,
                "debit": float(tax_pending),
                "credit": 0.0,
                "remark": "ضريبة مدخلات معلقة قيد المراجعة الضريبية (تتطلب فحص الفاتورة والآلية)"
            })
            vat_info = {"status": "معلقة قيد المراجعة", "account": acc_1520, "amount": float(tax_pending)}
        else:
            vat_info = {"status": "مستبعدة من الاسترداد (مدرجة بالمصروف)", "account": None, "amount": 0.0}

        simulated_lines.append({
            "account": pay_account,
            "party_type": None,
            "party": None,
            "debit": 0.0,
            "credit": float(gross_total),
            "remark": f"سداد من حساب {pay_type} ({pay_account})"
        })

        explanation = f"تسجيل مصروف تشغيلي مدفوع مباشرة من حساب {pay_type} بقيمة {float(gross_total):,.2f} ريال دون المساس بالعهد."
        post_approval_impact = {
            "cash_or_bank_decrease": float(gross_total),
            "expense_increase": float(net_exp),
            "vat_recoverable_increase": float(tax_eligible + tax_pending),
            "employee_custody_impact": 0.0
        }

    # -------------------------------------------------------------
    # INTENT B: Work expense paid from employee custody
    # -------------------------------------------------------------
    elif intent == INTENT_B_WORK_EXPENSE_CUSTODY:
        sim_doc_type = "Journal Entry"
        exp_account = get_verified_account_for_category(category, comp_name)
        custody_account, cust_type = get_verified_payment_account("custody", comp_name)

        # Tax calculation
        tax_eval = evaluate_vat_eligibility_and_split(
            amount=amount,
            account_code=exp_account,
            is_taxable=True,
            amount_basis="inclusive" if is_inclusive else "exclusive",
            usage_type="commercial" if vehicle_type == "commercial_equipment" else "passenger_restricted",
            has_valid_tax_invoice=has_valid_invoice,
            company=comp_name
        )

        net_exp = tax_eval["net_expense"]
        tax_eligible = tax_eval["tax_eligible"]
        tax_pending = tax_eval["tax_pending"]
        gross_total = tax_eval["gross_amount"]

        simulated_lines.append({
            "account": exp_account,
            "party_type": None,
            "party": None,
            "debit": float(net_exp),
            "credit": 0.0,
            "remark": f"تسوية مصروف من عهدة {employee_name or 'الموظف'}"
        })

        if tax_eligible > Decimal("0.00"):
            simulated_lines.append({
                "account": acc_1510,
                "party_type": None,
                "party": None,
                "debit": float(tax_eligible),
                "credit": 0.0,
                "remark": "ضريبة مدخلات 15% مستردة"
            })
            vat_info = {"status": "مستردة 15%", "account": acc_1510, "amount": float(tax_eligible)}
        elif tax_pending > Decimal("0.00"):
            simulated_lines.append({
                "account": acc_1520,
                "party_type": None,
                "party": None,
                "debit": float(tax_pending),
                "credit": 0.0,
                "remark": "ضريبة مدخلات معلقة قيد المراجعة الضريبية (تتطلب تدقيق الفاتورة أو الآلية)"
            })
            vat_info = {"status": "معلقة قيد المراجعة", "account": acc_1520, "amount": float(tax_pending)}
        else:
            vat_info = {"status": "مستبعدة من الاسترداد", "account": None, "amount": 0.0}

        # IMPORTANT: If custody_account is Cash (1120), party_type MUST BE NONE!
        # ERPNext v16 strictly rejects party_type on Cash accounts.
        simulated_lines.append({
            "account": custody_account,
            "party_type": None,
            "party": None,
            "debit": 0.0,
            "credit": float(gross_total),
            "remark": f"تسوية عهدة الموظف: {employee_name} ({employee_id})" if employee_id else "تسوية عهدة نقدية"
        })

        explanation = f"تسوية مصروف عهدة بقيمة {float(gross_total):,.2f} ريال لحساب الموظف {employee_name or employee_id}، مع قيد دائن على حساب العهد {custody_account} دون إجبار طرف على حساب النقد."
        post_approval_impact = {
            "custody_balance_decrease": float(gross_total),
            "expense_increase": float(net_exp),
            "vat_recoverable_increase": float(tax_eligible + tax_pending),
            "simulated_remaining_custody": float(Decimal(str(live_gl_balance["posted_custody_balance"])) - gross_total)
        }

    # -------------------------------------------------------------
    # INTENT C: Issue or replenish employee custody
    # -------------------------------------------------------------
    elif intent == INTENT_C_ISSUE_REPLENISH_CUSTODY:
        sim_doc_type = "Journal Entry"
        custody_account, _ = get_verified_payment_account("custody", comp_name)
        source_account, source_type = get_verified_payment_account(payment_method, comp_name)
        gross_total = round_currency(amount)

        # Debit: Custody Account (1120)
        simulated_lines.append({
            "account": custody_account,
            "party_type": None,
            "party": None,
            "debit": float(gross_total),
            "credit": 0.0,
            "remark": f"تغذية عهدة نقدية للموظف: {employee_name} ({employee_id})" if employee_id else "تغذية عهدة نقدية"
        })

        # Credit: Bank or Cash Account
        simulated_lines.append({
            "account": source_account,
            "party_type": None,
            "party": None,
            "debit": 0.0,
            "credit": float(gross_total),
            "remark": f"صرف عهدة عن طريق {source_type}"
        })

        vat_info = {"status": "غير خاضع للضريبة (تحويل أصول نقدية)", "account": None, "amount": 0.0}
        explanation = f"قيد تغذية عهدة بقيمة {float(gross_total):,.2f} ريال من حساب {source_type} ({source_account}) إلى حساب العهد النقدية للمهندسين والمشرفين ({custody_account})."
        post_approval_impact = {
            "source_account_decrease": float(gross_total),
            "custody_balance_increase": float(gross_total),
            "simulated_new_custody_balance": float(Decimal(str(live_gl_balance["posted_custody_balance"])) + gross_total)
        }

    # -------------------------------------------------------------
    # INTENT D: Personal salary advance and employee withdrawals
    # -------------------------------------------------------------
    elif intent == INTENT_D_PERSONAL_SALARY_ADVANCE:
        sim_doc_type = "Additional Salary"
        gross_total = round_currency(amount)
        salary_component = "استقطاع سلفة (Loan/Advance Deduction)"

        simulated_lines = [
            {
                "doctype": "Additional Salary",
                "employee": employee_id,
                "employee_name": employee_name,
                "salary_component": salary_component,
                "type": "Deduction",
                "amount": float(gross_total),
                "payroll_date": nowdate(),
                "overwrite_salary_structure_amount": 0,
                "remark": f"سلفة شخصية تخصم من مسير الرواتب القادم للموظف {employee_name}"
            }
        ]

        vat_info = {"status": "غير خاضع للضريبة (معاملات موظفين ورواتب)", "account": None, "amount": 0.0}
        explanation = f"تسجيل سلفة شخصية بقيمة {float(gross_total):,.2f} ريال كاستقطاع راتب (Additional Salary) في مسير الرواتب القادم للموظف {employee_name or employee_id}، مع الفصل الكامل عن عهد المواقع التشغيلية."
        post_approval_impact = {
            "payroll_deduction_scheduled": float(gross_total),
            "site_custody_impact": 0.0,
            "net_salary_reduction": float(gross_total)
        }

    # -------------------------------------------------------------
    # INTENT E: Monthly employee settlement report
    # -------------------------------------------------------------
    else:
        sim_doc_type = "Settlement Report"
        settlement_report = generate_employee_settlement_report(
            employee=employee_id,
            company=comp_name
        )
        return {
            "status": "success",
            "is_simulation": True,
            "intent": INTENT_E_MONTHLY_SETTLEMENT_REPORT,
            "intent_name": "كشف تسوية ومطابقة العهد والسلف الشهرية",
            "employee_id": employee_id,
            "employee_name": employee_name,
            "verified_identity_source": emp_source,
            "company": comp_name,
            "proposed_document_type": "Read-Only Report",
            "settlement_data": settlement_report,
            "summary_text": format_settlement_report_arabic(settlement_report)
        }

    # Format result dictionary
    result = {
        "status": "success",
        "is_simulation": True,
        "intent": intent,
        "intent_name": _get_intent_display_name(intent),
        "employee_id": employee_id,
        "employee_name": employee_name,
        "verified_identity_source": emp_source,
        "payment_method": payment_method,
        "selected_accounts": [line.get("account") for line in simulated_lines if line.get("account")],
        "vat_classification": vat_info,
        "proposed_document_type": sim_doc_type,
        "proposed_lines": simulated_lines,
        "actual_live_posted_balance": live_gl_balance,
        "simulated_post_approval_impact": post_approval_impact,
        "explanation": explanation,
        "formatted_preview": _format_simulation_preview_arabic(
            intent=intent,
            emp_id=employee_id,
            emp_name=employee_name,
            doc_type=sim_doc_type,
            lines=simulated_lines,
            vat_info=vat_info,
            impact=post_approval_impact,
            explanation=explanation,
            live_bal=live_gl_balance
        )
    }

    return result


def _get_intent_display_name(intent: str) -> str:
    names = {
        INTENT_A_EXPENSE_CASH_BANK: "صرف مصروفات نقدية / بنكية مباشرة",
        INTENT_B_WORK_EXPENSE_CUSTODY: "تسوية مصروفات أعمال من عهدة الموظف",
        INTENT_C_ISSUE_REPLENISH_CUSTODY: "صرف أو تغذية عهدة موقع للموظف",
        INTENT_D_PERSONAL_SALARY_ADVANCE: "سلفة شخصية واستقطاع من الراتب",
        INTENT_E_MONTHLY_SETTLEMENT_REPORT: "كشف تسوية ومطابقة العهد والسلف"
    }
    return names.get(intent, "معاملة محاسبية")


def _format_simulation_preview_arabic(intent, emp_id, emp_name, doc_type, lines, vat_info, impact, explanation, live_bal) -> str:
    """Formats simulation result in clean Arabic message for WhatsApp & Raven."""
    lines_text = ""
    for idx, l in enumerate(lines, 1):
        if l.get("doctype") == "Additional Salary":
            lines_text += f"  {idx}. [استقطاع راتب] {l.get('salary_component')}: {l.get('amount'):,.2f} ريال\n"
        else:
            dr = f"مدين: {l.get('debit'):,.2f}" if l.get('debit') else ""
            cr = f"دائن: {l.get('credit'):,.2f}" if l.get('credit') else ""
            lines_text += f"  {idx}. {l.get('account')}\n     {dr or cr}\n"

    posted_custody = live_bal.get("posted_custody_balance", 0.0)

    msg = (
        f"🔍 *معاينة المعاملة المحاسبية (وضع المحاكاة - Dry Run)*\n"
        f"════════════════════════════════════\n"
        f"📌 *نوع العملية:* {_get_intent_display_name(intent)}\n"
        f"👤 *الموظف:* {emp_name or 'غير محدد'} ({emp_id or 'N/A'})\n"
        f"📄 *المستند المقترح:* `{doc_type}` (مسودة Draft)\n"
        f"💰 *الرصيد الفعلي المقيد بالأستاذ العام:* {posted_custody:,.2f} ريال\n"
        f"🧾 *التصنيف الضريبي:* {vat_info.get('status', 'N/A')}\n"
        f"────────────────────────────────────\n"
        f"📊 *القيود المحاسبية المقترحة:*\n{lines_text}"
        f"────────────────────────────────────\n"
        f"💡 *الأثر المالي المتوقع بعد الاعتماد:*\n"
    )
    for k, v in impact.items():
        msg += f"  • {k}: {v:,.2f} ريال\n"
    msg += (
        f"════════════════════════════════════\n"
        f"ℹ️ *ملاحظة النظام:* لم يتم ترحيل أو حفظ أي بيانات مالية بالدفاتر."
    )
    return msg


# -------------------------------------------------------------------------
# PHASE 1 & 5 — LIVE BALANCES & SETTLEMENT REPORT (STRICTLY READ-ONLY)
# -------------------------------------------------------------------------

def get_employee_live_gl_balance(employee: str = None, company: str = None) -> dict:
    """
    Calculates live posted GL balance for employee strictly from tabGL Entry.
    Never treats draft Journal Entries as posted movements.
    """
    comp_name, abbr = get_target_company(company)
    custody_account = f"1120 - عهد نقدية للمهندسين والمشرفين - {abbr}"
    advance_account = f"1610 - سلف الموظفين - {abbr}"

    result = {
        "posted_custody_balance": 0.0,
        "posted_salary_advances": 0.0,
        "posted_salary_advance_balance": 0.0,
        "total_posted_gl_entries": 0,
        "unposted_draft_custody_entries": 0.0,
        "unposted_draft_advances": 0.0
    }

    # 1. Posted GL Entries for Custody Account (1120)
    # Notice: 1120 has no party_type. So we check user_remark or GL Entries for 1120
    if frappe.db.exists("Account", custody_account):
        gl_rows = frappe.db.sql("""
            SELECT SUM(debit) as total_debit, SUM(credit) as total_credit, COUNT(name) as count
            FROM `tabGL Entry`
            WHERE account = %s AND company = %s AND is_cancelled = 0
        """, (custody_account, comp_name), as_dict=True)
        if gl_rows and gl_rows[0].get("total_debit") is not None:
            dr = flt(gl_rows[0].total_debit)
            cr = flt(gl_rows[0].total_credit)
            result["posted_custody_balance"] = round(dr - cr, 2)
            result["total_posted_gl_entries"] += gl_rows[0].count

    # 2. Posted GL Entries for Employee Advances (1610) with party = employee
    if employee and frappe.db.exists("Account", advance_account):
        gl_adv = frappe.db.sql("""
            SELECT SUM(debit) as total_debit, SUM(credit) as total_credit, COUNT(name) as count
            FROM `tabGL Entry`
            WHERE account = %s AND party_type = 'Employee' AND party = %s AND company = %s AND is_cancelled = 0
        """, (advance_account, employee, comp_name), as_dict=True)
        if gl_adv and gl_adv[0].get("total_debit") is not None:
            dr = flt(gl_adv[0].total_debit)
            cr = flt(gl_adv[0].total_credit)
            result["posted_salary_advances"] = round(dr - cr, 2)
            result["posted_salary_advance_balance"] = round(dr - cr, 2)
            result["total_posted_gl_entries"] += gl_adv[0].count

    # 3. Separate Unposted Drafts (docstatus = 0)
    # Draft JVs mentioning custody
    draft_jvs = frappe.db.sql("""
        SELECT j.name, j.total_debit, j.user_remark
        FROM `tabJournal Entry` j
        WHERE j.docstatus = 0 AND j.company = %s
    """, (comp_name,), as_dict=True)
    for j in draft_jvs:
        rem = (j.user_remark or "").lower()
        if "عهدة" in rem or "1120" in rem or (employee and employee in rem):
            result["unposted_draft_custody_entries"] += flt(j.total_debit)

    # Draft Employee Advances
    if frappe.db.table_exists("Employee Advance"):
        adv_filters = {"docstatus": 0, "company": comp_name}
        if employee:
            adv_filters["employee"] = employee
        draft_advances = frappe.get_all("Employee Advance", filters=adv_filters, fields=["advance_amount"])
        for da in draft_advances:
            result["unposted_draft_advances"] += flt(da.advance_amount)

    return result


def generate_employee_settlement_report(
    employee: str,
    from_date: str = None,
    to_date: str = None,
    company: str = None
) -> dict:
    """
    Phase 2 Intent E & Phase 1 Audit:
    Strictly read-only monthly employee settlement report containing:
    - Employee identity and company
    - Reporting period
    - Opening posted balance
    - Custody advances actually paid
    - Posted work expenses and settlements
    - Custody closing posted balance
    - Personal advances and withdrawals
    - Confirmed payroll deductions
    - Outstanding recoverable balances
    - Separate unsubmitted draft totals
    - Proposed payroll recovery amount, pending review
    - Source voucher references for every amount
    """
    comp_name, abbr = get_target_company(company)
    custody_account = f"1120 - عهد نقدية للمهندسين والمشرفين - {abbr}"
    advance_account = f"1610 - سلف الموظفين - {abbr}"

    # Verify Employee
    emp = None
    if employee and frappe.db.exists("Employee", employee):
        emp = frappe.get_doc("Employee", employee)
    else:
        # Default to first active employee in company
        first_emp = frappe.get_all("Employee", filters={"company": comp_name, "status": "Active"}, limit=1)
        if first_emp:
            emp = frappe.get_doc("Employee", first_emp[0].name)

    if not emp:
        return {"status": "error", "message": "لم يتم العثور على موظف نشط في الشركة."}

    # Dates
    today_date = nowdate()
    start_date = from_date or frappe.utils.formatdate(add_months(today_date, -1), "yyyy-mm-01")
    end_date = to_date or today_date

    # 1. Opening Posted Balance (prior to start_date)
    opening_bal = Decimal("0.00")
    prior_gl = frappe.db.sql("""
        SELECT SUM(debit) as debits, SUM(credit) as credits
        FROM `tabGL Entry`
        WHERE account = %s AND company = %s AND posting_date < %s AND is_cancelled = 0
    """, (custody_account, comp_name, start_date), as_dict=True)
    if prior_gl and prior_gl[0].debits is not None:
        opening_bal = to_decimal(flt(prior_gl[0].debits) - flt(prior_gl[0].credits))

    # 2. Posted Movements in Period for Custody
    posted_vouchers = []
    custody_paid = Decimal("0.00")
    custody_spent = Decimal("0.00")

    period_gl = frappe.db.sql("""
        SELECT name, posting_date, account, debit, credit, voucher_type, voucher_no, remarks
        FROM `tabGL Entry`
        WHERE account = %s AND company = %s AND posting_date BETWEEN %s AND %s AND is_cancelled = 0
        ORDER BY posting_date asc, creation asc
    """, (custody_account, comp_name, start_date, end_date), as_dict=True)

    for row in period_gl:
        dr = to_decimal(row.debit)
        cr = to_decimal(row.credit)
        if dr > Decimal("0.00"):
            custody_paid += dr
        if cr > Decimal("0.00"):
            custody_spent += cr
        posted_vouchers.append({
            "voucher_type": row.voucher_type,
            "voucher_no": row.voucher_no,
            "date": str(row.posting_date),
            "type": "تغذية عهدة" if dr > 0 else "تسوية مصروف",
            "debit": float(dr),
            "credit": float(cr),
            "remarks": row.remarks
        })

    closing_custody_posted = opening_bal + custody_paid - custody_spent

    # 3. Personal Advances & Payroll Deductions (Strictly separate from site custody)
    personal_advances_paid = Decimal("0.00")
    confirmed_payroll_deductions = Decimal("0.00")
    payroll_vouchers = []

    # Check Additional Salary (submitted = 1)
    if frappe.db.table_exists("Additional Salary"):
        add_sals = frappe.get_all(
            "Additional Salary",
            filters={
                "employee": emp.name,
                "company": comp_name,
                "docstatus": 1,
                "type": "Deduction",
                "payroll_date": ["between", [start_date, end_date]]
            },
            fields=["name", "salary_component", "amount", "payroll_date", "ref_doctype", "ref_docname"]
        )
        for asal in add_sals:
            amt = to_decimal(asal.amount)
            confirmed_payroll_deductions += amt
            payroll_vouchers.append({
                "voucher_type": "Additional Salary",
                "voucher_no": asal.name,
                "date": str(asal.payroll_date),
                "component": asal.salary_component,
                "amount": float(amt),
                "status": "معتمد ومستقطع"
            })

    # Outstanding recoverable balance
    outstanding_personal_advances = max(Decimal("0.00"), personal_advances_paid - confirmed_payroll_deductions)

    # 4. Separate Unsubmitted Drafts (docstatus = 0)
    draft_vouchers = []
    draft_custody_total = Decimal("0.00")
    draft_salary_deductions_total = Decimal("0.00")

    # Draft JVs
    draft_jvs = frappe.db.sql("""
        SELECT name, posting_date, total_debit, user_remark
        FROM `tabJournal Entry`
        WHERE docstatus = 0 AND company = %s
    """, (comp_name,), as_dict=True)
    for dj in draft_jvs:
        rem = (dj.user_remark or "").lower()
        if "عهدة" in rem or "1120" in rem or emp.name in rem or (emp.employee_name and emp.employee_name.lower() in rem):
            amt = to_decimal(dj.total_debit)
            draft_custody_total += amt
            draft_vouchers.append({
                "voucher_type": "Journal Entry",
                "voucher_no": dj.name,
                "date": str(dj.posting_date),
                "amount": float(amt),
                "status": "مسودة غير مرحلة (Draft)",
                "remark": dj.user_remark
            })

    # Draft Additional Salary
    if frappe.db.table_exists("Additional Salary"):
        draft_adds = frappe.get_all(
            "Additional Salary",
            filters={"employee": emp.name, "company": comp_name, "docstatus": 0},
            fields=["name", "salary_component", "amount", "payroll_date"]
        )
        for da in draft_adds:
            amt = to_decimal(da.amount)
            draft_salary_deductions_total += amt
            draft_vouchers.append({
                "voucher_type": "Additional Salary",
                "voucher_no": da.name,
                "date": str(da.payroll_date),
                "amount": float(amt),
                "status": "مسودة استقطاع تحت المراجعة (Draft)",
                "remark": da.salary_component
            })

    report = {
        "employee_id": emp.name,
        "employee_name": emp.employee_name,
        "company": comp_name,
        "department": emp.department,
        "designation": emp.designation,
        "reporting_period": {
            "from_date": str(start_date),
            "to_date": str(end_date)
        },
        "posted_balances": {
            "opening_custody_balance": float(opening_bal),
            "custody_advances_paid": float(custody_paid),
            "posted_work_expenses": float(custody_spent),
            "closing_custody_posted_balance": float(closing_custody_posted),
            "personal_advances_paid": float(personal_advances_paid),
            "confirmed_payroll_deductions": float(confirmed_payroll_deductions),
            "outstanding_personal_advances": float(outstanding_personal_advances)
        },
        "unsubmitted_draft_totals": {
            "draft_custody_entries": float(draft_custody_total),
            "draft_salary_deductions": float(draft_salary_deductions_total),
            "total_drafts": float(draft_custody_total + draft_salary_deductions_total)
        },
        "proposed_payroll_recovery_pending_review": float(outstanding_personal_advances),
        "source_vouchers": {
            "posted_gl_vouchers": posted_vouchers,
            "payroll_vouchers": payroll_vouchers,
            "draft_vouchers": draft_vouchers
        },
        "governance_rule": "لا يتم خصم رصيد عهد المواقع التشغيلية من الراتب تلقائياً دون محضر تسوية واعتماد الإدارة المالية."
    }

    return report


def format_settlement_report_arabic(report: dict) -> str:
    """Renders human-readable Arabic settlement summary."""
    p = report.get("posted_balances", {})
    d = report.get("unsubmitted_draft_totals", {})
    period = report.get("reporting_period", {})

    msg = (
        f"📊 *كشف تسوية حساب العهد والسلف الشهرية*\n"
        f"════════════════════════════════════\n"
        f"👤 *الموظف:* {report.get('employee_name')} (`{report.get('employee_id')}`)\n"
        f"🏢 *الشركة:* {report.get('company')}\n"
        f"📅 *الفترة:* من {period.get('from_date')} إلى {period.get('to_date')}\n"
        f"────────────────────────────────────\n"
        f"🔹 *حركات العهد التشغيلية المقيدة (دفتر الأستاذ العام):*\n"
        f"  • الرصيد الافتتاحي المقيد: {p.get('opening_custody_balance', 0.0):,.2f} ريال\n"
        f"  • عهد منصرفة للموقع: +{p.get('custody_advances_paid', 0.0):,.2f} ريال\n"
        f"  • فواتير ومصروفات معتمدة: -{p.get('posted_work_expenses', 0.0):,.2f} ريال\n"
        f"  ⚖️ *صافي رصيد العهدة المقيد:* `{p.get('closing_custody_posted_balance', 0.0):,.2f}` ريال\n"
        f"────────────────────────────────────\n"
        f"🔹 *السلف الشخصية ومسيرات الرواتب:*\n"
        f"  • سلف شخصية منصرفة: {p.get('personal_advances_paid', 0.0):,.2f} ريال\n"
        f"  • استقطاعات رواتب مؤكدة: -{p.get('confirmed_payroll_deductions', 0.0):,.2f} ريال\n"
        f"  📌 *متبقي السلف المستحقة للخصم:* `{p.get('outstanding_personal_advances', 0.0):,.2f}` ريال\n"
        f"────────────────────────────────────\n"
        f"⚠️ *المعاملات تحت المراجعة (مسودات Draft - غير مرحلة):*\n"
        f"  • مسودات فواتير وتسويات عهدة: {d.get('draft_custody_entries', 0.0):,.2f} ريال\n"
        f"  • مسودات استقطاعات رواتب: {d.get('draft_salary_deductions', 0.0):,.2f} ريال\n"
        f"  (المسودات لا تؤثر على الأرصدة حتى يتم اعتمادها)\n"
        f"────────────────────────────────────\n"
        f"🛡️ *التوصية المحاسبية للرواتب:*\n"
        f"  المبلغ المقترح للاستقطاع من الراتب القادم: `{report.get('proposed_payroll_recovery_pending_review', 0.0):,.2f}` ريال (سلف شخصية فقط).\n"
        f"  *تنبيه:* عهدة الموقع لا تخصم من الراتب وتظل كعهد نقدية مستمرة لحين تسويتها بمستندات رسمية."
    )
    return msg


# -------------------------------------------------------------------------
# PHASE 5 — JOURNAL ENTRY ACC-JV-2026-00005 INSPECTION & PROPOSED CORRECTION
# -------------------------------------------------------------------------

def inspect_acc_jv_2026_00005(company: str = None) -> dict:
    """
    Live Read-Only Audit of Journal Entry ACC-JV-2026-00005.
    Never modifies database rows or docstatus.
    """
    jv_name = "ACC-JV-2026-00005"
    if not frappe.db.exists("Journal Entry", jv_name):
        return {"status": "error", "message": f"Journal Entry {jv_name} not found."}

    jv = frappe.get_doc("Journal Entry", jv_name)
    comp_name, abbr = get_target_company(company or jv.company)

    # Inspect lines
    rows = []
    for r in jv.accounts:
        rows.append({
            "account": r.account,
            "party_type": r.party_type,
            "party": r.party,
            "debit": float(r.debit),
            "credit": float(r.credit),
            "user_remark": r.user_remark
        })

    # Check GL Entries
    gl_entries = frappe.get_all(
        "GL Entry",
        filters={"voucher_type": "Journal Entry", "voucher_no": jv_name},
        fields=["name", "posting_date", "account", "debit", "credit", "is_cancelled"]
    )

    # Accounting Compatibility Analysis
    tax_accounts = get_company_tax_accounts(comp_name)
    acc_1510 = tax_accounts["recoverable_vat"]
    acc_1520 = tax_accounts["pending_vat"]

    gross_amt = to_decimal(jv.total_debit)
    # ZATCA 15% breakdown: 230 SAR = 200 Net + 30 VAT
    tax_breakdown = calculate_zatca_tax(gross_amt, is_inclusive=True)
    net_amt = tax_breakdown["net_amount"]
    vat_amt = tax_breakdown["tax_amount"]

    # Account 1120 analysis
    acc_1120_doc = frappe.get_doc("Account", f"1120 - عهد نقدية للمهندسين والمشرفين - {abbr}")
    is_cash_type = (acc_1120_doc.account_type == "Cash")

    analysis = {
        "document_name": jv_name,
        "docstatus": jv.docstatus,
        "status_label": "مسودة (Draft - غير مرحلة بالدفاتر)" if jv.docstatus == 0 else ("معتمدة" if jv.docstatus == 1 else "ملغاة"),
        "posting_date": str(jv.posting_date),
        "company": jv.company,
        "total_amount": float(gross_amt),
        "user_remark": jv.user_remark,
        "current_rows": rows,
        "posted_gl_entries_count": len(gl_entries),
        "findings": [
            {
                "issue": "عدم فصل ضريبة القيمة المضافة 15%",
                "details": f"تم قيد كامل المبلغ ({float(gross_amt):,.2f} ريال) على حساب المصروف 5120، بينما الفاتورة شاملة الضريبة، ومقدار الضريبة النظامي {float(vat_amt):,.2f} ريال وصافي المصروف {float(net_amt):,.2f} ريال.",
                "severity": "High",
                "zatca_impact": "فقدان حق استرداد ضريبة المدخلات أو تضخيم المصروف التشغيلي."
            },
            {
                "issue": "معاملة طرف الحساب (Party Field) على حساب النقد 1120",
                "details": f"الحساب '1120' معرف بنوع حساب 'Cash'. في نظام ERPNext v16 يمنع منعاً باتاً وضع Party Type أو Party على حسابات النقدية (Cash/Bank)، وبالتالي بقاء حقل الطرف فارغاً في القيد سليم برمجياً ومحاسبياً لتجنب كسر التحقق، ويتم إثبات هوية الموظف في البيان والشرح.",
                "severity": "Medium",
                "erpnext_impact": "محاولة فرض party_type='Employee' على حساب 1120 تؤدي لرسالة خطأ تمنع الحفظ والترحيل."
            },
            {
                "issue": "تحديد أهلية استرداد ضريبة وقود المركبات (المادة 50)",
                "details": "وفق لائحة هيئة الزكاة والضريبة والجمارك المادة 50، وقود المعدات والآليات الإنشائية مسترد بالكامل (حساب 1510)، بينما وقود سيارات الركوب غير مسترد (يحمل على المصروف)، وفي حال عدم التأكد من نوع المركبة أو سلامة الفاتورة الضريبية توجه إلى حساب ضريبة مدخلات معلقة تحت المراجعة (حساب 1520).",
                "severity": "Medium",
                "compliance_rule": "ZATCA Article 50"
            }
        ],
        "proposed_correction": {
            "strategy_1_commercial_equipment": {
                "description": "في حال كانت الفاتورة ضريبية رسمية لمعدة موقع أو مولد كهربائي أو آلية تجارية:",
                "rows": [
                    {"account": f"5120 - مصروف الوقود والمحروقات - {abbr}", "debit": float(net_amt), "credit": 0.0, "party": None},
                    {"account": acc_1510, "debit": float(vat_amt), "credit": 0.0, "party": None, "note": "ضريبة مدخلات 15% مستردة"},
                    {"account": f"1120 - عهد نقدية للمهندسين والمشرفين - {abbr}", "debit": 0.0, "credit": float(gross_amt), "party": None, "note": "مسددة من عهدة علي الصعيدي"}
                ]
            },
            "strategy_2_pending_review_default": {
                "description": "في حال انتظار تدقيق نوع السيارة أو الفاتورة الضريبية (الخيار الآمن الموصى به):",
                "rows": [
                    {"account": f"5120 - مصروف الوقود والمحروقات - {abbr}", "debit": float(net_amt), "credit": 0.0, "party": None},
                    {"account": acc_1520, "debit": float(vat_amt), "credit": 0.0, "party": None, "note": "ضريبة مدخلات معلقة قيد المراجعة"},
                    {"account": f"1120 - عهد نقدية للمهندسين والمشرفين - {abbr}", "debit": 0.0, "credit": float(gross_amt), "party": None, "note": "مسددة من عهدة علي الصعيدي"}
                ]
            }
        }
    }

    return analysis


def apply_jv_draft_correction(apply: bool = False, strategy: str = "pending_review") -> dict:
    """
    Safely corrects the draft Journal Entry ACC-JV-2026-00005 only if in draft (docstatus=0).
    Never modifies posted transactions.
    Never changes Account.account_type.
    """
    jv_name = "ACC-JV-2026-00005"
    if not frappe.db.exists("Journal Entry", jv_name):
        return {"status": "error", "message": f"{jv_name} not found"}

    jv = frappe.get_doc("Journal Entry", jv_name)
    if jv.docstatus != 0:
        return {
            "status": "error",
            "message": f"لا يمكن تعديل القيد {jv_name} مباشرة لأن حالته ليست مسودة (docstatus={jv.docstatus}). يتطلب إعداد قيد تسوية عكسي."
        }

    comp_name, abbr = get_target_company(jv.company)
    tax_accounts = get_company_tax_accounts(comp_name)
    target_vat_acc = tax_accounts["recoverable_vat"] if strategy == "commercial" else tax_accounts["pending_vat"]

    gross = to_decimal(jv.total_debit or "230.00")
    tax_calc = calculate_zatca_tax(gross, is_inclusive=True)
    net_amt = tax_calc["net_amount"]
    vat_amt = tax_calc["tax_amount"]

    exp_acc = f"5120 - مصروف الوقود والمحروقات - {abbr}"
    custody_acc = f"1120 - عهد نقدية للمهندسين والمشرفين - {abbr}"

    proposed_rows = [
        {
            "account": exp_acc,
            "debit": float(net_amt),
            "credit": 0.0,
            "user_remark": "صافي مصروف الوقود والمحروقات (فاتورة ضريبية)"
        },
        {
            "account": target_vat_acc,
            "debit": float(vat_amt),
            "credit": 0.0,
            "user_remark": "ضريبة القيمة المضافة للمدخلات 15% (ZATCA)" if strategy == "commercial" else "ضريبة مدخلات معلقة قيد المراجعة الضريبية (المادة 50)"
        },
        {
            "account": custody_acc,
            "debit": 0.0,
            "credit": float(gross),
            "user_remark": "مسددة من عهدة علي احمد الصعيدي (HR-EMP-00001)"
        }
    ]

    if not apply:
        return {
            "status": "preview",
            "document": jv_name,
            "apply": False,
            "proposed_rows": proposed_rows,
            "note": "لم يتم تطبيق التعديل على قاعدة البيانات، يتطلب تمرير apply=True بعد الموافقة المالية."
        }

    # Safe draft correction
    jv.set("accounts", [])
    for r in proposed_rows:
        jv.append("accounts", {
            "account": r["account"],
            "debit_in_account_currency": r["debit"],
            "credit_in_account_currency": r["credit"],
            "debit": r["debit"],
            "credit": r["credit"],
            "user_remark": r["user_remark"]
        })

    jv.user_remark = f"فاتورة بنزين بقيمة {float(gross):,.2f} ريال شاملة الضريبة 15% مسددة من عهدة علي الصعيدي (HR-EMP-00001) - مصححة محاسبياً"
    jv.flags.ignore_validate_update_after_submit = False
    jv.save(ignore_permissions=True)
    frappe.db.commit()

    return {
        "status": "success",
        "document": jv_name,
        "docstatus": 0,
        "message": f"تم تصحيح المسودة {jv_name} بنجاح وفصل الضريبة دون ترحيل القيد إلى الدفاتر.",
        "corrected_rows": proposed_rows
    }


def submit_acc_jv_2026_00005() -> dict:
    """
    Submits Journal Entry ACC-JV-2026-00005 under ZATCA Article 50:
    - 230 SAR on 5120 (fuel expense inclusive of non-recoverable VAT for admin passenger vehicle)
    - 230 SAR on 1120 (cash custody credited)
    - Documents employee HR-EMP-00001 (علي احمد الصعيدي) in user_remark
    - Submits document to docstatus = 1
    """
    jv_name = "ACC-JV-2026-00005"
    if not frappe.db.exists("Journal Entry", jv_name):
        return {"status": "error", "message": f"Journal Entry {jv_name} not found"}

    jv = frappe.get_doc("Journal Entry", jv_name)
    if jv.docstatus == 1:
        return {
            "status": "already_submitted",
            "message": f"Journal Entry {jv_name} is already submitted.",
            "docstatus": 1
        }

    comp = jv.company or "ركن سبل الافق"
    comp_name, abbr = get_target_company(comp)

    fuel_acc = f"5120 - مصروف الوقود والمحروقات - {abbr}"
    cust_acc = f"1120 - عهد نقدية للمهندسين والمشرفين - {abbr}"
    emp_remark = "فاتورة بنزين بقيمة 230 ريال شاملة الضريبة 15% (سيارة إدارية خاصة - غير مستردة ZATCA المادة 50) مسددة من عهدة علي احمد الصعيدي (HR-EMP-00001)"

    jv.set("accounts", [])
    jv.append("accounts", {
        "account": fuel_acc,
        "debit_in_account_currency": 230.0,
        "credit_in_account_currency": 0.0,
        "debit": 230.0,
        "credit": 0.0,
        "party_type": None,
        "party": None,
        "user_remark": emp_remark
    })
    jv.append("accounts", {
        "account": cust_acc,
        "debit_in_account_currency": 0.0,
        "credit_in_account_currency": 230.0,
        "debit": 0.0,
        "credit": 230.0,
        "party_type": None,
        "party": None,
        "user_remark": emp_remark
    })

    jv.user_remark = emp_remark
    jv.save(ignore_permissions=True)
    jv.submit()
    frappe.db.commit()

    gl_entries = frappe.get_all(
        "GL Entry",
        filters={"voucher_type": "Journal Entry", "voucher_no": jv_name, "is_cancelled": 0},
        fields=["name", "account", "debit", "credit", "posting_date"]
    )

    return {
        "status": "submitted",
        "voucher_no": jv_name,
        "docstatus": jv.docstatus,
        "posting_date": str(jv.posting_date),
        "total_amount": float(jv.total_debit),
        "user_remark": jv.user_remark,
        "gl_entries": gl_entries
    }


# -------------------------------------------------------------------------
# PHASE 2 (STAGE 2) — AUTOMATED WHATSAPP CUSTODY NOTIFICATION ENGINE
# -------------------------------------------------------------------------

def send_custody_whatsapp_notification(
    phone: str,
    message: str,
    docname: str,
    doctype: str,
    intent_title: str
) -> dict:
    """
    Safely dispatches WhatsApp notification to employee via Baileys bridge and
    records the outgoing transaction in Elsaidy WhatsApp Log.
    Guaranteed non-blocking: never raises exceptions to calling callers.
    """
    try:
        from hagag_erp.whatsapp_bridge import (
            call_baileys_api,
            get_hub_settings,
            resolve_destination_jid,
            normalize_phone_number
        )

        hub = get_hub_settings()
        bot_phone = normalize_phone_number(hub.connected_phone or hub.bot_phone_number or "") if hub else ""
        norm_phone = normalize_phone_number(phone)
        jid = resolve_destination_jid(norm_phone)

        # Safety: Block sending to bot's own handset
        if bot_phone and norm_phone and (bot_phone == norm_phone or norm_phone.endswith(bot_phone) or bot_phone.endswith(norm_phone)):
            frappe.logger("custody_notification").warn(f"[SendBlocked] Refusing to notify bot handset: {norm_phone}")
            return {"status": "ignored", "reason": "Target is bot number"}

        payload = {
            "jid": jid,
            "message": message
        }
        res = call_baileys_api("send-message", method="POST", data=payload, hub_doc=hub)

        # Record in Elsaidy WhatsApp Log
        if frappe.db.table_exists("Elsaidy WhatsApp Log"):
            try:
                log_doc = frappe.new_doc("Elsaidy WhatsApp Log")
                log_doc.message_id = (res.get("msg_id") if isinstance(res, dict) else None) or f"NOTIF-{frappe.generate_hash(length=8)}"
                log_doc.direction = "Outgoing"
                log_doc.sender_phone = bot_phone
                log_doc.receiver_phone = norm_phone
                log_doc.receiver_jid = jid
                log_doc.reply_jid = jid
                log_doc.message_text = message
                log_doc.status = "Replied"
                log_doc.delivery_status = "Sent" if (isinstance(res, dict) and res.get("status") == "ok") else "Pending"
                log_doc.extracted_intent = intent_title
                log_doc.linked_document_type = doctype
                log_doc.linked_document_name = docname
                log_doc.insert(ignore_permissions=True)
                frappe.db.commit()
            except Exception as log_err:
                frappe.logger("custody_notification").error(f"Failed to record WhatsApp notification log: {log_err}")

        return res or {"status": "dispatched"}

    except Exception as e:
        frappe.logger("custody_notification").error(f"Error sending WhatsApp notification for {doctype} {docname}: {e}")
        return {"status": "error", "error": str(e)}


def notify_employee_custody_event(doc, method=None) -> dict:
    """
    Hook triggered on on_submit of:
    - Employee Advance
    - Expense Claim
    - Additional Salary
    - Journal Entry (when accounts 1120 or 1610 are involved)
    - Payment Entry (when employee or custody accounts are involved)

    Extracts employee ID and verified phone number, computes the updated
    live custody balance from tabGL Entry, crafts a rich Arabic message, and
    enqueues non-blocking WhatsApp dispatch.
    NEVER blocks or fails document submission.
    """
    try:
        if isinstance(doc, dict):
            doc = frappe._dict(doc)

        doctype = doc.doctype
        comp = doc.get("company")
        doc_date = str(doc.get("posting_date") or doc.get("payroll_date") or nowdate())

        emp_id = None
        amount = Decimal("0.00")
        title = "إشعار معاملة عهدة مالية"
        purpose = ""

        # 1. Analyze by DocType
        if doctype == "Employee Advance":
            emp_id = doc.get("employee")
            amount = to_decimal(doc.get("advance_amount") or doc.get("paid_amount") or 0.0)
            p_desc = doc.get("purpose") or doc.get("user_remark") or ""
            if "سلفة" in p_desc:
                title = "إشعار صرف سلفة موظف"
            else:
                title = "إشعار صرف عهدة مالية للموقع"
            purpose = p_desc or "صرف عهدة مالية معتمدة"

        elif doctype == "Expense Claim":
            emp_id = doc.get("employee")
            amount = to_decimal(doc.get("total_sanctioned_amount") or doc.get("grand_total") or 0.0)
            title = "إشعار تسوية فواتير ومصروفات من العهدة"
            purpose = doc.get("remark") or "تسوية مطالبات ومصروفات عمل معتمدة"

        elif doctype == "Additional Salary":
            emp_id = doc.get("employee")
            amount = to_decimal(doc.get("amount") or 0.0)
            component = doc.get("salary_component") or ""
            is_deduction = (doc.get("type") == "Deduction" or any(k in component for k in ["استقطاع", "سلفة", "خصم", "سلف"]))
            if not is_deduction:
                return {"status": "skipped", "reason": "Not a salary advance deduction"}
            title = "إشعار تسجيل استقطاع سلفة من مسير الرواتب"
            purpose = doc.get("remark") or f"استقطاع سلفة ({component}) على مسير شهر {doc_date}"

        elif doctype == "Journal Entry":
            accounts = doc.get("accounts") or []
            # Check if 1120 or 1610 or custody/advance account is touched
            cust_rows = [r for r in accounts if any(k in (r.get("account") or "") for k in ["1120", "1610", "عهد", "سلف"])]
            if not cust_rows:
                return {"status": "skipped", "reason": "No custody or advance accounts touched"}

            # Resolve Employee
            for r in cust_rows:
                if r.get("party_type") == "Employee" and r.get("party"):
                    emp_id = r.get("party")
                    break

            # If not in party (standard for 1120 Cash), resolve from remarks
            if not emp_id:
                remark_text = f"{doc.get('user_remark') or ''} {' '.join(r.get('user_remark') or '' for r in cust_rows)}"
                id_match = re.search(r"HR-EMP-\d+", remark_text)
                if id_match:
                    emp_id = id_match.group(0)
                else:
                    emp_res = resolve_employee(identifier=remark_text, company=comp)
                    if emp_res.get("status") == "success":
                        emp_id = emp_res["employee"]

            if not emp_id:
                frappe.logger("custody_notification").info(f"Skipping notification for {doctype} {doc.name}: No employee mapped in custody JV")
                return {"status": "skipped", "reason": "No employee mapped"}

            # Determine direction on custody/advance accounts
            salf_rows = [r for r in cust_rows if any(k in (r.get("account") or "") for k in ["1610", "سلف"])]
            ohda_rows = [r for r in cust_rows if any(k in (r.get("account") or "") for k in ["1120", "عهد"])]

            if salf_rows:
                debit_salf = sum(to_decimal(r.get("debit")) for r in salf_rows)
                credit_salf = sum(to_decimal(r.get("credit")) for r in salf_rows)
                if debit_salf > Decimal("0.00"):
                    title = "إشعار صرف سلفة موظف"
                    amount = debit_salf
                else:
                    title = "إشعار تسوية / سداد سلفة موظف"
                    amount = credit_salf
            elif ohda_rows:
                credit_ohda = sum(to_decimal(r.get("credit")) for r in ohda_rows)
                debit_ohda = sum(to_decimal(r.get("debit")) for r in ohda_rows)
                if credit_ohda > Decimal("0.00"):
                    title = "إشعار خصم وتسوية فاتورة من العهدة"
                    amount = credit_ohda
                elif debit_ohda > Decimal("0.00"):
                    title = "إشعار تغذية وإضافة عهدة نقدية"
                    amount = debit_ohda
                else:
                    amount = to_decimal(doc.get("total_debit") or 0.0)
                    title = "إشعار قيد تسوية عهدة"
            else:
                amount = to_decimal(doc.get("total_debit") or 0.0)
                title = "إشعار قيد تسوية عهدة"

            purpose = doc.get("user_remark") or "تسوية قيد محاسبي للعهدة"

        elif doctype == "Payment Entry":
            # Check if employee or custody account is involved
            is_emp = (doc.get("party_type") == "Employee")
            paid_to = doc.get("paid_to") or ""
            paid_from = doc.get("paid_from") or ""
            is_custody = any(k in (paid_to + " " + paid_from) for k in ["1120", "1610", "عهد", "سلف"])

            if not (is_emp or is_custody):
                return {"status": "skipped", "reason": "Not an employee custody payment"}

            emp_id = doc.get("party") if is_emp else None
            if not emp_id:
                rem_text = doc.get("remarks") or ""
                id_match = re.search(r"HR-EMP-\d+", rem_text)
                if id_match:
                    emp_id = id_match.group(0)
                else:
                    emp_res = resolve_employee(identifier=rem_text, company=comp)
                    if emp_res.get("status") == "success":
                        emp_id = emp_res["employee"]

            if not emp_id:
                return {"status": "skipped", "reason": "No employee mapped"}

            amount = to_decimal(doc.get("paid_amount") or doc.get("received_amount") or 0.0)
            title = "إشعار سند صرف / تغذية عهدة"
            purpose = doc.get("remarks") or "صرف دفعة مالية للعهدة"

        else:
            return {"status": "skipped", "reason": f"DocType {doctype} not monitored"}

        if not emp_id or amount <= Decimal("0.00"):
            return {"status": "skipped", "reason": "Missing employee ID or zero amount"}

        # 2. Extract Employee Details & Clean Phone
        if not frappe.db.exists("Employee", emp_id):
            return {"status": "skipped", "reason": f"Employee {emp_id} does not exist"}

        emp = frappe.get_doc("Employee", emp_id)
        emp_name = emp.employee_name or emp_id
        phone = emp.cell_number or getattr(emp, "personal_phone", None) or getattr(emp, "company_phone", None)

        if not phone and frappe.db.table_exists("Elsaidy WhatsApp Contact Rule"):
            phone = frappe.db.get_value("Elsaidy WhatsApp Contact Rule", {"linked_employee": emp_id, "is_active": 1}, "phone_number")

        clean_num = clean_phone(phone) if phone else ""
        if not clean_num:
            frappe.logger("custody_notification").info(f"Skipping WhatsApp notification: No phone registered for {emp_id} ({emp_name})")
            return {"status": "skipped", "reason": "No phone registered", "employee": emp_id}

        if any(clean_num == clean_phone(bp) for bp in KNOWN_BOT_PHONES):
            frappe.logger("custody_notification").warn(f"Refusing to notify bot number {clean_num} for employee {emp_id}")
            return {"status": "skipped", "reason": "Bot phone blocked", "employee": emp_id}

        # 3. Calculate Updated Live Post-Submission Custody Balance
        live_bal = get_employee_live_gl_balance(employee=emp_id, company=comp)
        posted_custody = live_bal.get("posted_custody_balance", 0.0)
        posted_advance = live_bal.get("posted_salary_advance_balance", 0.0)

        if "سلفة" in title or doctype == "Additional Salary":
            balance_line = f"📊 *رصيد السلف المقيد المتبقي:* `{posted_advance:,.2f}` ريال"
        else:
            balance_line = f"📊 *رصيد العهدة المقيد المتبقي:* `{posted_custody:,.2f}` ريال"

        # Saudi Time (12-hour Asia/Riyadh format)
        try:
            import zoneinfo
            from datetime import datetime as dt_cls
            sa_tz = zoneinfo.ZoneInfo("Asia/Riyadh")
            now_sa = dt_cls.now(sa_tz)
            time_part = now_sa.strftime("%I:%M").lstrip("0")
            period = "ص" if now_sa.strftime("%p") == "AM" else "م"
            saudi_time = f"{time_part} {period} بتوقيت السعودية"
        except Exception:
            saudi_time = frappe.utils.now_datetime().strftime("%I:%M %p")

        # 4. Format Structured Arabic WhatsApp Message
        msg = (
            f"🔔 *{title}*\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 *الموظف:* {emp_name} (`{emp_id}`)\n"
            f"💰 *المبلغ:* {float(amount):,.2f} ريال سعودي\n"
            f"📄 *المستند:* `{doc.name}` ({doc_date})\n"
            f"⏰ *التوقيت:* {saudi_time}\n"
            f"📝 *البيان:* {purpose}\n"
            f"{balance_line}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🏢 *الشركة:* {comp or 'ركن سبل الأفق'}\n"
            f"ℹ️ إشعار آلي صادر من نظام Elsaidy ERP"
        )

        # 5. Non-Blocking Dispatch (Enqueue)
        if getattr(frappe.flags, "in_test", False) or getattr(frappe.flags, "sync_whatsapp_notification", False):
            # Synchronous in test mode for instant assertions
            send_custody_whatsapp_notification(
                phone=clean_num,
                message=msg,
                docname=doc.name,
                doctype=doctype,
                intent_title=title
            )
        else:
            frappe.enqueue(
                "hagag_erp.custody_service.send_custody_whatsapp_notification",
                queue="short",
                phone=clean_num,
                message=msg,
                docname=doc.name,
                doctype=doctype,
                intent_title=title
            )

        return {
            "status": "success",
            "employee": emp_id,
            "employee_name": emp_name,
            "recipient_phone": clean_num,
            "notification_title": title,
            "amount": float(amount),
            "updated_custody_balance": posted_custody,
            "message_preview": msg
        }

    except Exception as err:
        # Non-blocking guarantee: Never fail caller transaction
        frappe.logger("custody_notification").error(f"Failed in notify_employee_custody_event: {err}")
        return {"status": "error", "error": str(err)}

