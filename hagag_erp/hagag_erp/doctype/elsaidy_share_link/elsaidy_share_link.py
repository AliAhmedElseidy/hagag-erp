# Copyright (c) 2026, Elsaidy ERP and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime, get_datetime, add_to_date


class ElsaidyShareLink(Document):
    def before_insert(self):
        if not self.token:
            self.token = frappe.generate_hash(length=32)
        if not self.expires_at:
            self.expires_at = add_to_date(now_datetime(), days=7)
        self.share_url = f"/shared_dashboard?token={self.token}"

    @frappe.whitelist()
    def revoke(self):
        """Immediately revokes this share link."""
        self.is_revoked = 1
        self.save(ignore_permissions=True)
        frappe.db.commit()
        return {"status": "success", "message": "تم إلغاء الرابط فوراً بنجاح."}
