# Copyright (c) 2026, Elsaidy ERP and Contributors
# License: MIT. See LICENSE

import frappe
from frappe import _


def _check_financial_permission():
    """Ensure session user has permission to view financial statements / GL Entry."""
    if frappe.session.user == "Administrator":
        return True

    allowed_roles = {
        "System Manager",
        "Accounts Manager",
        "Accounts User",
        "Auditor",
        "CEO",
        "Director",
    }
    user_roles = set(frappe.get_roles(frappe.session.user))
    if allowed_roles.intersection(user_roles):
        return True

    if frappe.has_permission("GL Entry", "read"):
        return True

    frappe.throw(_("Not permitted to view financial metrics"), frappe.PermissionError)


@frappe.whitelist()
def get_employee_custody_balance(filters=None):
    """
    Returns the real-time net balance of employee custody account
    '1120 - عهد نقدية للمهندسين والمشرفين - Rkn' for company 'ركن سبل الافق'.
    Debit - Credit gives the unliquidated custody balance held by employees.
    """
    _check_financial_permission()
    company = "ركن سبل الافق"
    account = "1120 - عهد نقدية للمهندسين والمشرفين - Rkn"

    res = frappe.db.sql(
        """
        SELECT COALESCE(SUM(debit - credit), 0) as balance
        FROM `tabGL Entry`
        WHERE account = %s AND company = %s AND is_cancelled = 0
        """,
        (account, company),
        as_dict=True,
    )

    balance = float(res[0].balance) if res else 0.0
    return {"value": balance, "fieldtype": "Currency"}


@frappe.whitelist()
def get_bank_balance(filters=None):
    """
    Returns the real-time net balance of bank account
    '1201 - البنك الأهلي السعودي (SNB) - Rkn' for company 'ركن سبل الافق'.
    """
    _check_financial_permission()
    company = "ركن سبل الافق"
    account = "1201 - البنك الأهلي السعودي (SNB) - Rkn"

    res = frappe.db.sql(
        """
        SELECT COALESCE(SUM(debit - credit), 0) as balance
        FROM `tabGL Entry`
        WHERE account = %s AND company = %s AND is_cancelled = 0
        """,
        (account, company),
        as_dict=True,
    )

    balance = float(res[0].balance) if res else 0.0
    return {"value": balance, "fieldtype": "Currency"}


@frappe.whitelist()
def get_cash_balance(filters=None):
    """
    Returns the real-time net balance of cash account
    '1110 - نقد - Rkn' for company 'ركن سبل الافق'.
    """
    _check_financial_permission()
    company = "ركن سبل الافق"
    account = "1110 - نقد - Rkn"

    res = frappe.db.sql(
        """
        SELECT COALESCE(SUM(debit - credit), 0) as balance
        FROM `tabGL Entry`
        WHERE account = %s AND company = %s AND is_cancelled = 0
        """,
        (account, company),
        as_dict=True,
    )

    balance = float(res[0].balance) if res else 0.0
    return {"value": balance, "fieldtype": "Currency"}


@frappe.whitelist()
def get_operating_expenses(filters=None):
    """
    Returns the total posted operating expenses (Account Group 5xxx + Input VAT 1510)
    for company 'ركن سبل الافق'.
    """
    _check_financial_permission()
    company = "ركن سبل الافق"

    res = frappe.db.sql(
        """
        SELECT COALESCE(SUM(debit - credit), 0) as total
        FROM `tabGL Entry`
        WHERE (account LIKE '5%%' OR account LIKE '1510%%')
          AND company = %s
          AND is_cancelled = 0
        """,
        (company,),
        as_dict=True,
    )

    total = float(res[0].total) if res else 0.0
    return {"value": total, "fieldtype": "Currency"}
