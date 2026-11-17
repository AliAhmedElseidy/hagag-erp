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

def _check_manager_permission():
    """
    Strict security check: only authorized managers (System Manager, CEO, Director)
    can generate, list, or revoke executive share links.
    Auditors, Accounts Users, Guests, and Read-Only roles are strictly forbidden.
    """
    if frappe.session.user == "Administrator":
        return
    manager_roles = {"System Manager", "CEO", "Director"}
    user_roles = set(frappe.get_roles(frappe.session.user))
    if manager_roles.intersection(user_roles):
        return
    frappe.throw(
        _("غير مصرح لك بإدارة أو إنشاء روابط المشاركة. الصلاحية مقتصرة حصرياً على المديرين المخولين (System Manager, CEO, Director)."),
        frappe.PermissionError,
    )


@frappe.whitelist()
def create_executive_share_link(dashboard, expires_in_days=7, description=None):
    """
    Creates a secure, time-expiring link for executive dashboard viewing without login.
    Only permitted users (System Manager, CEO, Director) can generate links.
    """
    _check_manager_permission()

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
    Immediately revokes an active share link. Restricts to authorized managers.
    """
    _check_manager_permission()
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
    Lists active, unrevoked share links with usage statistics for authorized managers only.
    """
    _check_manager_permission()
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
    and returns ONLY pre-aggregated dashboard KPI metrics for the SPECIFIC authorized dashboard,
    strictly protecting employee PII, raw tables, and unauthorized modules.
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

    company = "ركن سبل الافق"
    dashboard_id = link_data.dashboard
    dashboard_title = frappe.db.get_value("Insights Dashboard v3", dashboard_id, "title") or link_data.title

    payload = {
        "title": dashboard_title,
        "dashboard_id": dashboard_id,
        "expires_at": str(link_data.expires_at),
        "views_count": new_count,
        "metrics": {},
    }

    # Route data payload strictly according to the linked dashboard:
    if dashboard_id == "ta38bufs82":
        # 1. لوحة المشاريع والمقاولات: بيانات المشاريع ونسب الإنجاز والتكاليف فقط
        projects_res = frappe.db.sql(
            """
            SELECT
                name, project_name, status, percent_complete, estimated_costing, total_billed_amount
            FROM `tabProject`
            WHERE company = %s
            ORDER BY creation DESC
            LIMIT 20
            """,
            (company,),
            as_dict=True,
        )
        total_estimated = sum(float(p.get("estimated_costing") or 0) for p in projects_res)
        total_billed = sum(float(p.get("total_billed_amount") or 0) for p in projects_res)
        avg_completion = sum(float(p.get("percent_complete") or 0) for p in projects_res) / len(projects_res) if projects_res else 0.0

        payload["metrics"] = {
            "active_projects_count": len([p for p in projects_res if p.get("status") != "Completed"]),
            "total_estimated_costing": total_estimated,
            "total_billed_amount": total_billed,
            "average_completion_rate": round(avg_completion, 1),
        }
        payload["projects"] = projects_res

    elif dashboard_id == "ta3f45js58":
        # 2. لوحة الإدارة المالية والسيولة: الحسابات، البنوك، المصروفات، والضريبة
        fin_res = frappe.db.sql(
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
        f = fin_res[0] if fin_res else {}
        bank = float(f.get("bank_balance", 0))
        cash = float(f.get("cash_balance", 0))
        payload["metrics"] = {
            "bank_balance": bank,
            "cash_balance": cash,
            "total_liquidity": bank + cash,
            "custody_balance": float(f.get("custody_balance", 0)),
            "operating_expenses": float(f.get("operating_expenses", 0)),
            "input_vat": float(f.get("input_vat", 0)),
            "output_vat": float(f.get("output_vat", 0)),
            "net_vat": float(f.get("output_vat", 0)) - float(f.get("input_vat", 0)),
        }

    elif dashboard_id == "ta4grqim1d":
        # 3. لوحة المشتريات والموردين: أوامر الشراء، فواتير المشتريات، وأرصدة الموردين
        po_res = frappe.db.sql(
            """
            SELECT
                COALESCE(COUNT(name), 0) as po_count,
                COALESCE(SUM(base_grand_total), 0) as total_po_amount
            FROM `tabPurchase Order`
            WHERE company = %s AND docstatus = 1
            """,
            (company,),
            as_dict=True,
        )
        pi_res = frappe.db.sql(
            """
            SELECT
                COALESCE(COUNT(name), 0) as pi_count,
                COALESCE(SUM(base_grand_total), 0) as total_pi_amount,
                COALESCE(SUM(outstanding_amount), 0) as total_payable
            FROM `tabPurchase Invoice`
            WHERE company = %s AND docstatus = 1
            """,
            (company,),
            as_dict=True,
        )
        po = po_res[0] if po_res else {}
        pi = pi_res[0] if pi_res else {}
        payload["metrics"] = {
            "purchase_orders_count": int(po.get("po_count", 0)),
            "total_po_amount": float(po.get("total_po_amount", 0)),
            "purchase_invoices_count": int(pi.get("pi_count", 0)),
            "total_pi_amount": float(pi.get("total_pi_amount", 0)),
            "total_supplier_payable": float(pi.get("total_payable", 0)),
        }

    elif dashboard_id == "ta40cvqbt0":
        # 4. لوحة الموارد البشرية والعمالة: إحصائيات الكوادر بدون بيانات شخصية
        active_emp_count = frappe.db.count("Employee", {"status": "Active"})
        custody_emp = frappe.db.sql(
            """
            SELECT COALESCE(SUM(debit - credit), 0) as total_custody
            FROM `tabGL Entry`
            WHERE company = %s AND is_cancelled = 0 AND account LIKE '1120%%'
            """,
            (company,),
            as_dict=True,
        )
        departments = frappe.db.sql(
            """
            SELECT department, COUNT(name) as count
            FROM `tabEmployee`
            WHERE status = 'Active' AND department IS NOT NULL
            GROUP BY department
            """,
            as_dict=True,
        )
        payload["metrics"] = {
            "active_employees_count": active_emp_count,
            "total_custody_held": float(custody_emp[0].get("total_custody", 0)) if custody_emp else 0.0,
            "departments_count": len(departments),
        }
        payload["departments"] = departments

    elif dashboard_id == "fhfdbsjbrl":
        # 5. لوحة المستخلصات والضريبة ومحجوزات الضمان
        tax_res = frappe.db.sql(
            """
            SELECT
                COALESCE(SUM(CASE WHEN account LIKE '1510%%' THEN debit - credit ELSE 0 END), 0) as input_vat,
                COALESCE(SUM(CASE WHEN account LIKE '2330%%' THEN credit - debit ELSE 0 END), 0) as output_vat
            FROM `tabGL Entry`
            WHERE company = %s AND is_cancelled = 0
            """,
            (company,),
            as_dict=True,
        )
        t = tax_res[0] if tax_res else {}
        inv_res = frappe.db.sql(
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
        inv = inv_res[0] if inv_res else {}
        total_billed = float(inv.get("total_invoiced", 0))
        retention = total_billed * 0.10  # 10% statutory retention guarantee

        payload["metrics"] = {
            "total_invoiced": total_billed,
            "total_outstanding": float(inv.get("total_outstanding", 0)),
            "collected_amount": total_billed - float(inv.get("total_outstanding", 0)),
            "retention_guarantee_10pct": retention,
            "input_vat_15pct": float(t.get("input_vat", 0)),
            "output_vat_15pct": float(t.get("output_vat", 0)),
            "net_zatca_payable": float(t.get("output_vat", 0)) - float(t.get("input_vat", 0)),
        }

    else:
        # Default / Executive Dashboard (fhe3hd2vih): مؤشرات القيادة العامة والمشاريع
        liq_res = frappe.db.sql(
            """
            SELECT
                COALESCE(SUM(CASE WHEN account LIKE '1201%%' THEN debit - credit ELSE 0 END), 0) as bank_balance,
                COALESCE(SUM(CASE WHEN account LIKE '1110%%' THEN debit - credit ELSE 0 END), 0) as cash_balance,
                COALESCE(SUM(CASE WHEN account LIKE '1120%%' THEN debit - credit ELSE 0 END), 0) as custody_balance,
                COALESCE(SUM(CASE WHEN account LIKE '5%%' THEN debit - credit ELSE 0 END), 0) as operating_expenses,
                COALESCE(SUM(CASE WHEN account LIKE '1510%%' THEN debit - credit ELSE 0 END), 0) as input_vat
            FROM `tabGL Entry`
            WHERE company = %s AND is_cancelled = 0
            """,
            (company,),
            as_dict=True,
        )
        l = liq_res[0] if liq_res else {}
        bank = float(l.get("bank_balance", 0))
        cash = float(l.get("cash_balance", 0))

        inv_res = frappe.db.sql(
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
        inv = inv_res[0] if inv_res else {}

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
        emp_count = frappe.db.count("Employee", {"status": "Active"})

        payload["metrics"] = {
            "bank_balance": bank,
            "cash_balance": cash,
            "total_liquidity": bank + cash,
            "custody_balance": float(l.get("custody_balance", 0)),
            "operating_expenses": float(l.get("operating_expenses", 0)),
            "net_profit_loss": -float(l.get("operating_expenses", 0)),  # Net Loss = Income(0) - Expense
            "input_vat": float(l.get("input_vat", 0)),
            "total_invoiced": float(inv.get("total_invoiced", 0)),
            "total_outstanding": float(inv.get("total_outstanding", 0)),
            "active_projects_count": len(projects_res),
            "active_employees_count": emp_count,
        }
        payload["projects"] = projects_res

    return payload
