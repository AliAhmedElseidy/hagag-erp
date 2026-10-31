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
	def validate(self):
		if self.bot_phone_number:
			self.bot_phone_number = normalize_phone_number(self.bot_phone_number)

	@frappe.whitelist()
	def refresh_status(self):
		status = get_hub_status_internal(self)
		self.reload()
		return status

	@frappe.whitelist()
	def request_pairing(self, phone=None):
		phone = phone or self.bot_phone_number
		if not phone:
			frappe.throw("يرجى إدخال رقم هاتف البوت أولاً لطلب كود الربط.")
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
