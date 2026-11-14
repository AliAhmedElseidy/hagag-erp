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


class ElsaidyWhatsAppHub(Document):
	def onload(self):
		try:
			get_hub_status_internal(self)
		except Exception:
			pass

	def validate(self):
		if self.bot_phone_number:
			self.bot_phone_number = normalize_phone_number(self.bot_phone_number)
		if getattr(self, "connected_phone", None):
			self.connected_phone = normalize_phone_number(self.connected_phone)
		# Normalize all contact phones in allowlist
		for c in (getattr(self, "allowed_direct_contacts", []) or []):
			if getattr(c, "phone_number", None):
				c.phone_number = normalize_phone_number(c.phone_number)
		# Enforce strict allowlist defaults: zero auto-reply to unregistered senders
		self.allow_unregistered_direct = 0
		self.allow_unregistered_groups = 0
		self.unregistered_auto_reply = ""

	def on_update(self):
		try:
			frappe.cache().delete_value("whatsapp_active_contact_rules")
			frappe.cache().delete_value("whatsapp_hub_settings")
		except Exception:
			pass

	@frappe.whitelist()
	def refresh_status(self):
		status = get_hub_status_internal(self)
		self.reload()
		return status

	@frappe.whitelist()
	def request_pairing(self, phone=None):
		phone = phone or self.bot_phone_number
		if not phone:
			frappe.throw("الرجاء إدخال رقم الهاتف أولاً لطلب رمز الإقران.")
		return request_pairing_code_internal(self, phone)

	@frappe.whitelist()
	def get_qr(self):
		return get_qr_code_internal(self)

	@frappe.whitelist()
	def sync_groups(self):
		return fetch_whatsapp_groups_internal(self)

	@frappe.whitelist()
	def restart_service(self):
		return restart_baileys_internal(self)

	@frappe.whitelist()
	def logout_service(self):
		return logout_baileys_internal(self)
