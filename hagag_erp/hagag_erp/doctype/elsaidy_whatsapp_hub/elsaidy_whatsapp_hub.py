# Copyright (c) 2026, Elsaidy ERP and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from hagag_erp.whatsapp_bridge import (
	normalize_phone_number,
	call_baileys_api,
	get_hub_status_internal,
	request_pairing_code_internal,
	get_qr_code_internal,
	fetch_whatsapp_groups_internal,
	restart_baileys_internal,
	logout_baileys_internal
)
from hagag_erp.whatsapp_bridge import require_hub_permission


class ElsaidyWhatsAppHub(Document):
	def onload(self):
		try:
			get_hub_status_internal(self)
		except Exception:
			pass

	def validate(self):
		if self.bot_phone_number:
			self.bot_phone_number = normalize_phone_number(self.bot_phone_number)

	@frappe.whitelist()
	def refresh_status(self):
		require_hub_permission("read")
		status = get_hub_status_internal(self)
		self.reload()
		return status

	@frappe.whitelist()
	def request_pairing(self, phone=None):
		require_hub_permission("write", admin=True)
		phone = phone or self.bot_phone_number
		if not phone:
			frappe.throw("الرجاء إدخال رقم الهاتف أولاً لطلب رمز الإقران.")
		return request_pairing_code_internal(self, phone)

	@frappe.whitelist()
	def get_qr(self):
		require_hub_permission("write", admin=True)
		return get_qr_code_internal(self)

	@frappe.whitelist()
	def sync_groups(self):
		require_hub_permission("write")
		return fetch_whatsapp_groups_internal(self)

	@frappe.whitelist()
	def restart_service(self):
		require_hub_permission("write", admin=True)
		return restart_baileys_internal(self)

	@frappe.whitelist()
	def logout_service(self):
		require_hub_permission("write", admin=True)
		return logout_baileys_internal(self)
