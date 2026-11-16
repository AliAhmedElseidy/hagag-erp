# Copyright (c) 2026, Elsaidy ERP and Contributors
# License: MIT. See LICENSE

import json
import frappe
from frappe import _
from frappe.utils import now_datetime, get_datetime, add_to_date


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
        "Executive Director (Read Only)",
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
    Returns the total posted operating expenses (Account Group 5xxx)
    for company 'ركن سبل الافق'.
    Note: Input VAT 1510 is a recoverable asset from ZATCA and is NOT an expense.
    """
    _check_financial_permission()
    company = "ركن سبل الافق"

    res = frappe.db.sql(
        """
        SELECT COALESCE(SUM(debit - credit), 0) as total
        FROM `tabGL Entry`
        WHERE account LIKE '5%%'
          AND company = %s
          AND is_cancelled = 0
        """,
        (company,),
        as_dict=True,
    )

    total = float(res[0].total) if res else 0.0
    return {"value": total, "fieldtype": "Currency"}


@frappe.whitelist()
def get_input_vat_balance(filters=None):
    """
    Returns the recoverable Input VAT balance (Account 1510) for company 'ركن سبل الافق'.
    """
    _check_financial_permission()
    company = "ركن سبل الافق"
    res = frappe.db.sql(
        """
        SELECT COALESCE(SUM(debit - credit), 0) as total
        FROM `tabGL Entry`
        WHERE account LIKE '1510%%'
          AND company = %s
          AND is_cancelled = 0
        """,
        (company,),
        as_dict=True,
    )
    total = float(res[0].total) if res else 0.0
    return {"value": total, "fieldtype": "Currency"}


# -------------------------------------------------------------
# Manager Portal (Executive Read-Only & Secure Share Link API)
# -------------------------------------------------------------

@frappe.whitelist()
def create_executive_share_link(dashboard, expires_in_days=7, description=None):
    """
    Creates a secure, time-expiring link for executive dashboard viewing without login.
    Only permitted users (System Manager, CEO, Director) can generate links.
    """
    _check_financial_permission()

    if not frappe.db.exists("Insights Dashboard v3", dashboard):
        frappe.throw(_("لوحة المؤشرات المحددة غير موجودة: {0}").format(dashboard))

    dash_title = frappe.db.get_value("Insights Dashboard v3", dashboard, "title") or dashboard
    expires_at = add_to_date(now_datetime(), days=int(expires_in_days or 7))

    doc = frappe.new_doc("Elsaidy Share Link")
    doc.title = f"مشاركة: {dash_title}"
    doc.dashboard = dashboard
    doc.expires_at = expires_at
    doc.description = description or ""
    doc.insert(ignore_permissions=True)
    frappe.db.commit()

    return {
        "status": "success",
        "name": doc.name,
        "token": doc.token,
        "share_url": doc.share_url,
        "expires_at": str(doc.expires_at),
    }


@frappe.whitelist()
def revoke_executive_share_link(token):
    """
    Immediately revokes an active share link.
    """
    _check_financial_permission()
    name = frappe.db.get_value("Elsaidy Share Link", {"token": token}, "name")
    if not name:
        frappe.throw(_("رابط المشاركة غير موجود"))

    doc = frappe.get_doc("Elsaidy Share Link", name)
    doc.is_revoked = 1
    doc.save(ignore_permissions=True)
    frappe.db.commit()
    return {"status": "success", "message": "تم إلغاء صلاحية الرابط فوراً"}


@frappe.whitelist()
def list_active_share_links():
    """
    Lists active, unrevoked share links with usage statistics.
    """
    _check_financial_permission()
    links = frappe.get_all(
        "Elsaidy Share Link",
        filters={"is_revoked": 0},
        fields=[
            "name",
            "title",
            "dashboard",
            "token",
            "expires_at",
            "share_url",
            "views_count",
            "last_accessed_at",
            "last_accessed_ip",
            "creation",
        ],
        order_by="creation desc",
    )
    return links


@frappe.whitelist(allow_guest=True)
def get_shared_dashboard_data(token):
    """
    Secure endpoint for Guest access via expiring share token.
    Validates token, checks expiry/revocation, records access log,
    and returns ONLY pre-aggregated dashboard KPI metrics without exposing raw database tables.
    """
    if not token or not isinstance(token, str) or len(token) < 16:
        frappe.throw(_("رابط غير صالح أو مفقود"), frappe.PermissionError)

    link_data = frappe.db.get_value(
        "Elsaidy Share Link",
        {"token": token},
        ["name", "dashboard", "title", "expires_at", "is_revoked", "views_count", "access_log"],
        as_dict=True,
    )

    if not link_data:
        frappe.throw(_("رابط المشاهدة غير موجود"), frappe.PermissionError)

    if link_data.is_revoked:
        frappe.throw(_("تم إلغاء صلاحية هذا الرابط بواسطة الإدارة"), frappe.PermissionError)

    if now_datetime() > get_datetime(link_data.expires_at):
        frappe.throw(_("انتهت صلاحية هذا الرابط في: {0}").format(link_data.expires_at), frappe.PermissionError)

    # Log access audit trail
    req_ip = getattr(frappe.local, "request_ip", "") or "Unknown"
    now_str = str(now_datetime())[:19]
    user_agent = (getattr(frappe.local, "request", None) and frappe.local.request.headers.get("User-Agent", "")) or ""
    log_entry = f"[{now_str}] IP: {req_ip} | UA: {user_agent[:60]}\n"

    new_count = (link_data.views_count or 0) + 1
    new_log = (link_data.access_log or "") + log_entry

    frappe.db.set_value(
        "Elsaidy Share Link",
        link_data.name,
        {
            "views_count": new_count,
            "last_accessed_at": now_datetime(),
            "last_accessed_ip": req_ip,
            "access_log": new_log[-2000:],  # keep last 2000 chars
        },
        update_modified=False,
    )
    frappe.db.commit()

    # Pre-aggregate safe contracting executive metrics
    company = "ركن سبل الافق"

    # Liquidity
    liquidity_res = frappe.db.sql(
        """
        SELECT
            COALESCE(SUM(CASE WHEN account LIKE '1201%%' THEN debit - credit ELSE 0 END), 0) as bank_balance,
            COALESCE(SUM(CASE WHEN account LIKE '1110%%' THEN debit - credit ELSE 0 END), 0) as cash_balance,
            COALESCE(SUM(CASE WHEN account LIKE '1120%%' THEN debit - credit ELSE 0 END), 0) as custody_balance,
            COALESCE(SUM(CASE WHEN account LIKE '5%%' THEN debit - credit ELSE 0 END), 0) as operating_expenses,
            COALESCE(SUM(CASE WHEN account LIKE '1510%%' THEN debit - credit ELSE 0 END), 0) as input_vat,
            COALESCE(SUM(CASE WHEN account LIKE '2330%%' THEN credit - debit ELSE 0 END), 0) as output_vat
        FROM `tabGL Entry`
        WHERE company = %s AND is_cancelled = 0
        """,
        (company,),
        as_dict=True,
    )
    liq = liquidity_res[0] if liquidity_res else {}

    # Contracts & Invoicing
    invoice_res = frappe.db.sql(
        """
        SELECT
            COALESCE(COUNT(name), 0) as total_invoices,
            COALESCE(SUM(base_grand_total), 0) as total_invoiced,
            COALESCE(SUM(outstanding_amount), 0) as total_outstanding
        FROM `tabSales Invoice`
        WHERE company = %s AND docstatus = 1
        """,
        (company,),
        as_dict=True,
    )
    inv = invoice_res[0] if invoice_res else {}

    # Active Projects
    projects_res = frappe.db.sql(
        """
        SELECT
            name, project_name, status, percent_complete, estimated_costing, total_billed_amount
        FROM `tabProject`
        WHERE company = %s AND status != 'Completed'
        ORDER BY creation DESC
        LIMIT 10
        """,
        (company,),
        as_dict=True,
    )

    # Active Employees count
    emp_count = frappe.db.count("Employee", {"status": "Active"})

    dashboard_title = frappe.db.get_value("Insights Dashboard v3", link_data.dashboard, "title") or link_data.title

    return {
        "title": dashboard_title,
        "expires_at": str(link_data.expires_at),
        "views_count": new_count,
        "metrics": {
            "bank_balance": float(liq.get("bank_balance", 0)),
            "cash_balance": float(liq.get("cash_balance", 0)),
            "total_liquidity": float(liq.get("bank_balance", 0)) + float(liq.get("cash_balance", 0)),
            "custody_balance": float(liq.get("custody_balance", 0)),
            "operating_expenses": float(liq.get("operating_expenses", 0)),
            "input_vat": float(liq.get("input_vat", 0)),
            "output_vat": float(liq.get("output_vat", 0)),
            "net_vat": float(liq.get("output_vat", 0)) - float(liq.get("input_vat", 0)),
            "total_invoiced": float(inv.get("total_invoiced", 0)),
            "total_outstanding": float(inv.get("total_outstanding", 0)),
            "collected_amount": float(inv.get("total_invoiced", 0)) - float(inv.get("total_outstanding", 0)),
            "active_projects_count": len(projects_res),
            "active_employees_count": emp_count,
        },
        "projects": projects_res,
    }
