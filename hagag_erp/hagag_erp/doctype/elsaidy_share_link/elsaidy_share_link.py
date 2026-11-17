# Copyright (c) 2026, Elsaidy ERP and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime, get_datetime, add_to_date


class ElsaidyShareLink(Document):
    def validate(self):
        from hagag_erp.dashboard_api import _check_manager_permission
        _check_manager_permission()

    def before_insert(self):
        from hagag_erp.dashboard_api import _check_manager_permission
        _check_manager_permission()

        if not self.token:
            self.token = frappe.generate_hash(length=32)
        if not self.expires_at:
            self.expires_at = add_to_date(now_datetime(), days=7)
        self.share_url = f"/shared_dashboard?token={self.token}"

    def on_trash(self):
        from hagag_erp.dashboard_api import _check_manager_permission
        _check_manager_permission()

    @frappe.whitelist()
    def revoke(self):
        """Immediately revokes this share link."""
        from hagag_erp.dashboard_api import _check_manager_permission
        _check_manager_permission()

        self.is_revoked = 1
        self.save(ignore_permissions=True)
        frappe.db.commit()
        return {"status": "success", "message": "تم إلغاء الرابط فوراً بنجاح."}
