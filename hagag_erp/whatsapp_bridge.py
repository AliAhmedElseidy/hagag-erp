# Copyright (c) 2026, Elsaidy ERP and contributors
# For license information, please see license.txt

import re
import time
import json
from decimal import Decimal
import requests
import frappe
from frappe import _
from frappe.utils import now_datetime, cint, flt

ARABIC_TO_ASCII_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")


def normalize_phone_number(number: str) -> str:
	"""
	Normalizes Egyptian, Saudi, and international phone numbers into clean digits:
	- Egypt: 010..., 011..., 012..., 015... -> 201...
	- Saudi: 05..., 5... -> 9665...
	- International: removes +, spaces, hyphens, and leading 00.
	"""
	if not number:
		return ""

	n = str(number).translate(ARABIC_TO_ASCII_DIGITS)
	n = re.sub(r"\D", "", n)

	if n.startswith("00"):
		n = n[2:]

	# Egypt local: 010..., 011..., 012..., 015... (11 digits) -> 201...
	if re.match(r"^0(1[0125]\d{8})$", n):
		return "20" + n[1:]
	# Egypt without 0: 10..., 11..., 12..., 15... (10 digits) -> 20...
	elif re.match(r"^(1[0125]\d{8})$", n):
		return "20" + n
	# Saudi local: 05xxxxxxxx (10 digits) -> 9665xxxxxxxx
	elif re.match(r"^0(5\d{8})$", n):
		return "966" + n[1:]
	# Saudi without 0: 5xxxxxxxx (9 digits) -> 9665xxxxxxxx
	elif re.match(r"^(5\d{8})$", n):
		return "966" + n

	return n


def get_hub_settings(hub_doc=None):
	"""Retrieves Elsaidy WhatsApp Hub single settings."""
	if hub_doc:
		return hub_doc
	try:
		return frappe.get_single("Elsaidy WhatsApp Hub")
	except Exception:
		return None


def call_baileys_api(endpoint: str, method: str = "GET", data: dict = None, hub_doc=None) -> dict:
	"""Executes HTTP request to local Baileys bridge container with Bearer token auth."""
	hub = get_hub_settings(hub_doc)
	base_url = (hub.baileys_url if hub and hub.baileys_url else "http://wa-baileys:3000").rstrip("/")
	api_token = hub.get_password("api_token") if (hub and hasattr(hub, "get_password") and hub.get_password("api_token")) else "HAGAG_WA_7f3c9a2d6e4b8a1c"

	url = f"{base_url}/{endpoint.lstrip('/')}"
	headers = {
		"Authorization": f"Bearer {api_token}",
		"x-api-token": api_token,
		"Content-Type": "application/json"
	}

	try:
		if method.upper() == "POST":
			resp = requests.post(url, json=data or {}, headers=headers, timeout=15)
		else:
			resp = requests.get(url, headers=headers, timeout=15)

		try:
			return resp.json()
		except Exception:
			return {"status": "error", "http_status": resp.status_code, "text": resp.text}
	except Exception as exc:
		frappe.log_error(f"Baileys API Request Failed ({endpoint}): {str(exc)}", "Elsaidy WhatsApp Hub")
		return {"status": "error", "error": str(exc)}


def get_hub_status_internal(hub_doc=None) -> dict:
	"""Queries Baileys /status and updates the Hub document state."""
	hub = get_hub_settings(hub_doc)
	res = call_baileys_api("status", method="GET", hub_doc=hub)

	is_connected = bool(res.get("connected"))
	conn_status = "Connected" if is_connected else (
		"Connecting" if res.get("connection_status") == "connecting" else "Disconnected"
	)
	bot_phone = res.get("bot_phone") or ""

	if hub:
		frappe.db.set_value("Elsaidy WhatsApp Hub", None, {
			"connection_status": conn_status,
			"connected_phone": bot_phone,
			"last_sync_time": now_datetime()
		}, update_modified=False)
		frappe.db.commit()

	return {
		"status": conn_status,
		"connected": is_connected,
		"bot_phone": bot_phone,
		"raw": res
	}


def request_pairing_code_internal(hub_doc, phone: str) -> dict:
	"""Requests an 8-character pairing code for the supplied phone number."""
	clean_phone = normalize_phone_number(phone)
	if not clean_phone:
		frappe.throw(_("رقم الهاتف غير صالح"))

	res = call_baileys_api("pair-phone", method="POST", data={"phone": clean_phone}, hub_doc=hub_doc)

	if res.get("status") == "ok":
		code = res.get("code")
		formatted = res.get("formatted_code") or (f"{code[:4]}-{code[4:]}" if code and len(code) == 8 else code)
		frappe.db.set_value("Elsaidy WhatsApp Hub", None, {
			"bot_phone_number": clean_phone,
			"connection_status": "Connecting",
			"last_sync_time": now_datetime()
		}, update_modified=False)
		frappe.db.commit()

		return {
			"status": "ok",
			"code": code,
			"formatted_code": formatted,
			"phone": clean_phone
		}

	if res.get("status") == "already_connected":
		return res

	error_msg = res.get("error") or res.get("message") or "فشل طلب رمز الإقران من خدمة Baileys"
	frappe.throw(_(f"لم يتم إنشاء رمز الإقران: {error_msg}"))


def get_qr_code_internal(hub_doc=None) -> dict:
	"""Fetches the latest QR code Data URL for modal display."""
	return call_baileys_api("qr", method="GET", hub_doc=hub_doc)


def fetch_whatsapp_groups_internal(hub_doc=None) -> dict:
	"""Fetches participating groups from Baileys and syncs them to Hub child table."""
	hub = get_hub_settings(hub_doc)
	res = call_baileys_api("groups", method="GET", hub_doc=hub)

	if res.get("status") != "ok":
		frappe.throw(_(f"فشل جلب المجموعات: {res.get('error', 'لا يوجد رد')}"))

	incoming_groups = res.get("groups", [])
	hub_doc = frappe.get_doc("Elsaidy WhatsApp Hub")

	existing_jids = {row.group_jid: row for row in hub_doc.allowed_groups}
	updated_count = 0
	added_count = 0

	for grp in incoming_groups:
		jid = grp.get("jid")
		name = grp.get("name") or "مجموعة بدون اسم"
		count = cint(grp.get("participants_count", 0))

		if jid in existing_jids:
			row = existing_jids[jid]
			row.group_name = name
			row.participants_count = count
			updated_count += 1
		else:
			hub_doc.append("allowed_groups", {
				"group_jid": jid,
				"group_name": name,
				"participants_count": count,
				"is_active": 1,
				"auto_reply_in_group": 1,
				"require_mention": 0
			})
			added_count += 1

	hub_doc.save(ignore_permissions=True)
	frappe.db.commit()

	return {
		"status": "ok",
		"count": len(incoming_groups),
		"added": added_count,
		"updated": updated_count
	}


def restart_baileys_internal(hub_doc=None) -> dict:
	"""Sends restart command to Baileys."""
	return call_baileys_api("restart", method="POST", hub_doc=hub_doc)


def logout_baileys_internal(hub_doc=None) -> dict:
	"""Sends logout and session wipe command to Baileys."""
	res = call_baileys_api("logout", method="POST", hub_doc=hub_doc)
	frappe.db.set_value("Elsaidy WhatsApp Hub", None, {
		"connection_status": "Disconnected",
		"connected_phone": None,
		"last_sync_time": now_datetime()
	}, update_modified=False)
	frappe.db.commit()
	return res


# ──────────────────────────────────────────────────────────────────────────────
# AI Reply Engine
# ──────────────────────────────────────────────────────────────────────────────

def call_ai_api(user_message: str, provider: str, api_key: str, model: str, system_prompt: str) -> str:
	"""
	Calls an AI provider API (Gemini or OpenAI-compatible) and returns the response text.
	Falls back to an Arabic error message if the call fails.
	"""
	if not api_key or not model:
		return "عذراً، لم يتم تهيئة مفتاح الذكاء الاصطناعي. تواصل مع مدير النظام."

	try:
		if provider == "Gemini":
			url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
			payload = {
				"contents": [
					{"role": "user", "parts": [{"text": user_message}]}
				],
				"systemInstruction": {
					"parts": [{"text": system_prompt or "أنت المساعد الذكي لشركة الصعيدي للمقاولات."}]
				},
				"generationConfig": {
					"maxOutputTokens": 512,
					"temperature": 0.7
				}
			}
			resp = requests.post(url, json=payload, timeout=25)
			data = resp.json()

			if resp.status_code != 200:
				err = data.get("error", {}).get("message", str(resp.status_code))
				frappe.log_error(f"Gemini API Error: {err}", "Elsaidy WhatsApp Hub AI")
				return f"عذراً، حدث خطأ في الذكاء الاصطناعي. [{err[:60]}]"

			candidates = data.get("candidates", [])
			if not candidates:
				return "عذراً، لم أتمكن من معالجة طلبك. حاول مرة أخرى."

			return (
				candidates[0]
				.get("content", {})
				.get("parts", [{}])[0]
				.get("text", "عذراً، لم أفهم طلبك. حاول مرة أخرى.")
			)

		elif provider in ("OpenAI", "Custom API"):
			url = "https://api.openai.com/v1/chat/completions"
			headers = {
				"Authorization": f"Bearer {api_key}",
				"Content-Type": "application/json"
			}
			payload = {
				"model": model,
				"messages": [
					{"role": "system", "content": system_prompt or "أنت مساعد ذكي محترف."},
					{"role": "user", "content": user_message}
				],
				"max_tokens": 512,
				"temperature": 0.7
			}
			resp = requests.post(url, json=payload, headers=headers, timeout=25)
			data = resp.json()

			if resp.status_code != 200:
				err = data.get("error", {}).get("message", str(resp.status_code))
				frappe.log_error(f"OpenAI API Error: {err}", "Elsaidy WhatsApp Hub AI")
				return f"عذراً، حدث خطأ في الذكاء الاصطناعي. [{err[:60]}]"

			return data["choices"][0]["message"]["content"]

		else:
			return "مزود الذكاء الاصطناعي غير معروف. تواصل مع مدير النظام."

	except requests.Timeout:
		frappe.log_error("AI API Timeout", "Elsaidy WhatsApp Hub AI")
		return "عذراً، انتهت مهلة الرد من الذكاء الاصطناعي. حاول مرة أخرى."
	except Exception as e:
		frappe.log_error(f"AI API Exception: {str(e)}", "Elsaidy WhatsApp Hub AI")
		return f"عذراً، حدث خطأ في معالجة طلبك. [{str(e)[:50]}]"


# ──────────────────────────────────────────────────────────────────────────────
# Whitelisted API Endpoints
# ──────────────────────────────────────────────────────────────────────────────

@frappe.whitelist()
def send_test_whatsapp_message(recipient: str, message: str) -> dict:
	"""Whitelisted helper to send test message from Frappe GUI."""
	clean_recipient = recipient.strip()
	is_group = clean_recipient.endswith("@g.us")
	jid = clean_recipient if is_group else f"{normalize_phone_number(clean_recipient)}@s.whatsapp.net"

	payload = {
		"jid": jid,
		"message": message
	}
	return call_baileys_api("send-message", method="POST", data=payload)


@frappe.whitelist()
def wipe_baileys_session() -> dict:
	"""
	Whitelisted endpoint to trigger a hard session wipe on the Baileys container.
	Useful when recovering from Bad MAC / libsignal decrypt errors / 401 states.
	"""
	hub = get_hub_settings()
	result = call_baileys_api("wipe-session", method="POST", hub_doc=hub)

	# Update hub status to Disconnected after wipe
	try:
		frappe.db.set_value("Elsaidy WhatsApp Hub", None, {
			"connection_status": "Disconnected",
			"connected_phone": None,
			"last_sync_time": now_datetime()
		}, update_modified=False)
		frappe.db.commit()
	except Exception:
		pass

	return result


@frappe.whitelist()
def get_baileys_logs(limit: int = 100) -> dict:
	"""
	Whitelisted endpoint to fetch the in-memory log ring buffer from Baileys.
	Returns up to 100 recent log entries (newest first).
	"""
	hub = get_hub_settings()
	clean_limit = min(cint(limit) or 100, 100)
	result = call_baileys_api(f"logs?limit={clean_limit}", method="GET", hub_doc=hub)
	return result


def parse_expense_from_text(text: str) -> dict:
	"""
	Parses Arabic natural language expense messages for amount, VAT inclusiveness, description, and vendor.
	Examples:
	- 'صرفت 500 ريال وقود محطة الأمانة'
	- 'دفعت مبلغ مقداره 1200 ريال أجرة نقل من شركة المحمدية'
	- 'اشتريت خردة 350 ريال لمشروع الرياض'
	"""
	if not text:
		return None

	normalized_text = text.translate(ARABIC_TO_ASCII_DIGITS)

	# Keywords indicating an expense / purchase
	expense_keywords = ["صرف", "دفع", "اشتر", "أشتري", "أشتر", "سدد", "سدّد", "صُرف", "مصاريف", "مدفوع", "اشتريت", "دفعت", "صرفت", "فاتورة"]
	has_keyword = any(kw in normalized_text for kw in expense_keywords)
	if not has_keyword:
		return None

	# Extract numeric amount (supports decimals e.g. 1200 or 1200.50)
	amount_match = re.search(r"(?:مبلغ|قيمة|مقدار|بقيمة|مبلغه)?\s*([0-9]+(?:[\.,][0-9]{1,2})?)\s*(?:ريال|ر\.س|SAR)?", normalized_text)
	if not amount_match:
		return None

	raw_amount_str = amount_match.group(1).replace(",", ".")
	try:
		amount = Decimal(raw_amount_str)
		if amount <= 0:
			return None
	except Exception:
		return None

	# Determine VAT inclusion
	is_inclusive = True
	if "قبل الضريبة" in normalized_text or "بدون ضريبة" in normalized_text or "غير شامل" in normalized_text:
		is_inclusive = False
	elif "شامل" in normalized_text or "مع الضريبة" in normalized_text:
		is_inclusive = True

	# Extract vendor / supplier if present ("من شركة ...", "من محطة ...", "من مورد ...")
	vendor = None
	vendor_match = re.search(r"من\s+(شركة|محطة|مورد|مشروع|متجر|محل)?\s*([^\n\.,]+)", normalized_text)
	if vendor_match:
		vendor = vendor_match.group(0).strip()

	return {
		"is_expense": True,
		"amount": amount,
		"is_inclusive": is_inclusive,
		"original_text": text,
		"vendor": vendor
	}


def send_baileys_reply(jid: str, text: str, quoted_msg_id: str = None) -> dict:
	"""Helper to send reply via Baileys API."""
	payload = {
		"jid": jid,
		"message": text,
		"quoted_message_id": quoted_msg_id
	}
	return call_baileys_api("send-message", method="POST", data=payload)


@frappe.whitelist(allow_guest=True)
def receive_baileys_event():
	"""
	Core Webhook Endpoint invoked by Baileys Node.js container on 'messages.upsert'.
	Enforces:
	1. API Token Authentication.
	2. Idempotency on 'msg_id' (operation_id = f"WA-{msg_id}").
	3. Rule Verification for Direct Chat and Groups.
	4. Bot Mode Routing: AI + Accounting Hybrid / Accounting Only / AI Only / Disabled.
	5. ZATCA Tax Engine Integration (strictly Draft docstatus=0).
	6. AI Reply via Gemini / OpenAI if enabled.
	7. Quoted WhatsApp response with ERPNext direct URL.
	8. Comprehensive logging into 'Elsaidy WhatsApp Log'.
	"""
	start_time = time.time()
	req = frappe.request

	# 1. Authenticate Token
	auth_header = req.headers.get("Authorization", "")
	api_token_header = req.headers.get("x-api-token", "")
	hub = get_hub_settings()
	expected_token = hub.get_password("api_token") if (hub and hasattr(hub, "get_password") and hub.get_password("api_token")) else "HAGAG_WA_7f3c9a2d6e4b8a1c"

	is_authed = (auth_header == f"Bearer {expected_token}") or (api_token_header == expected_token)
	if not is_authed:
		frappe.response["http_status_code"] = 401
		return {"error": "Unauthorized"}

	# Parse Payload
	try:
		payload = req.get_json() or {}
	except Exception:
		payload = {}

	# Support both direct payload (from new index.js) and nested payload
	event_type = payload.get("event_type") or payload.get("event")
	if event_type not in ("message", "messages.upsert"):
		return {"status": "ignored", "reason": "Not a message event"}

	# Support both flat payload (new) and nested data (old)
	data = payload if payload.get("message_id") else payload.get("data", payload)

	msg_id = data.get("message_id") or data.get("msg_id")
	if not msg_id:
		return {"status": "error", "reason": "Missing msg_id / message_id"}

	is_group = bool(data.get("is_group"))
	group_jid = data.get("remote_jid") if is_group else data.get("group_jid", "")
	sender_jid = data.get("sender_jid") or ""
	sender_phone = normalize_phone_number(data.get("sender_phone") or "")
	sender_name = data.get("push_name") or data.get("sender_name") or ""
	text = (data.get("text") or "").strip()
	has_media = bool(data.get("has_media"))
	remote_jid = data.get("remote_jid") or ""

	# Re-derive group_jid if missing
	if is_group and not group_jid:
		group_jid = remote_jid

	# 2. Read Bot Mode & AI Settings
	bot_mode = (hub.bot_mode if hub and hub.bot_mode else "AI + Accounting Hybrid")
	enable_ai = cint(hub.enable_ai_reply if hub else 0)
	ai_provider = (hub.ai_provider if hub and hub.ai_provider else "Gemini")
	ai_api_key = None
	if hub and enable_ai:
		try:
			ai_api_key = hub.get_password("ai_api_key") or None
		except Exception:
			ai_api_key = None
	ai_model = (hub.ai_model if hub and hub.ai_model else "gemini-2.5-flash")
	ai_system_prompt = (
		hub.ai_system_prompt
		if hub and hub.ai_system_prompt
		else "أنت المساعد الذكي لشركة الصعيدي للمقاولات. ترد باللغة العربية بأسلوب مهني محترم."
	)

	# 3. Strict Idempotency Check (WA-{msg_id})
	existing_log = frappe.db.get_value(
		"Elsaidy WhatsApp Log",
		{"message_id": msg_id},
		["name", "status", "linked_document_type", "linked_document_name"],
		as_dict=True
	)
	if existing_log and existing_log.status in ("Processed", "Replied"):
		return {
			"status": "already_processed",
			"message_id": msg_id,
			"linked_doc": f"{existing_log.linked_document_type} - {existing_log.linked_document_name}"
		}

	# Create/prepare log entry
	log_doc = frappe.new_doc("Elsaidy WhatsApp Log")
	log_doc.message_id = msg_id
	log_doc.direction = "Incoming"
	log_doc.sender_phone = sender_phone
	log_doc.sender_name = sender_name
	log_doc.is_group = 1 if is_group else 0
	log_doc.group_jid = group_jid
	log_doc.message_text = text
	log_doc.status = "Received"

	# Target JID for replies
	reply_jid = group_jid if is_group else (f"{sender_phone}@s.whatsapp.net" if sender_phone else sender_jid)

	# 4. Access Control & Permission Rules Verification
	target_project = None
	target_cost_center = hub.default_cost_center if hub else None
	target_custody_account = None
	company = hub.default_company if (hub and hub.default_company) else "شركة ركن سبل الأفق للمقاولات"
	contact_rule = None
	group_rule = None

	if is_group:
		# Group Rule Check
		matching_groups = [r for r in hub.allowed_groups if r.group_jid == group_jid and r.is_active] if hub else []
		if matching_groups:
			group_rule = matching_groups[0]
			log_doc.group_name = group_rule.group_name
			target_project = group_rule.default_project
			target_cost_center = group_rule.default_cost_center or target_cost_center
			target_custody_account = group_rule.default_custody_account

			if group_rule.require_mention:
				bot_phone = hub.connected_phone or hub.bot_phone_number or ""
				if bot_phone and bot_phone not in text and "@" not in text:
					log_doc.status = "Ignored"
					log_doc.error_message = "Group message ignored (require_mention active and bot not tagged)"
					log_doc.insert(ignore_permissions=True)
					frappe.db.commit()
					return {"status": "ignored", "reason": "No mention"}
		else:
			if not (hub and hub.allow_unregistered_groups):
				log_doc.status = "Ignored"
				log_doc.error_message = f"Unregistered group: {group_jid}"
				log_doc.insert(ignore_permissions=True)
				frappe.db.commit()
				return {"status": "ignored", "reason": "Unregistered group"}
	else:
		# Direct 1-to-1 Rule Check
		matching_contacts = [
			c for c in hub.allowed_direct_contacts
			if c.is_active and normalize_phone_number(c.phone_number) == sender_phone
		] if hub else []

		if matching_contacts:
			contact_rule = matching_contacts[0]
			target_project = contact_rule.default_project
			target_cost_center = contact_rule.default_cost_center or target_cost_center
			target_custody_account = contact_rule.default_custody_account
		else:
			if not (hub and hub.allow_unregistered_direct):
				unregistered_msg = hub.unregistered_auto_reply if (hub and hub.unregistered_auto_reply) else (
					"عذراً، لست مرخصاً للتفاعل مع بوت Elsaidy ERP. تواصل معنا من خلال القنوات الرسمية."
				)
				if hub and hub.auto_reply_enabled:
					send_baileys_reply(reply_jid, unregistered_msg, quoted_msg_id=msg_id)

				log_doc.status = "Ignored"
				log_doc.reply_text = unregistered_msg
				log_doc.error_message = f"Unregistered direct sender: {sender_phone}"
				log_doc.insert(ignore_permissions=True)
				frappe.db.commit()
				return {"status": "rejected", "reason": "Unregistered contact"}

	# ── 5. Intent Detection & Bot Mode Routing ────────────────────────────────
	reply_content = None
	created_doc = None

	# Short-circuit: if bot is disabled, just log
	if bot_mode == "Disabled / Log Only":
		log_doc.extracted_intent = "Disabled Mode - Log Only"
		log_doc.status = "Ignored"
		log_doc.insert(ignore_permissions=True)
		frappe.db.commit()
		return {"status": "ok", "message_id": msg_id, "log": log_doc.name, "mode": "disabled"}

	parsed_expense = parse_expense_from_text(text)

	# ── ZATCA Expense Path ────────────────────────────────────────────────────
	if parsed_expense and bot_mode != "AI Assistant Only":
		log_doc.extracted_intent = "Expense Record"

		# Verify permission
		if contact_rule and not contact_rule.can_record_expenses:
			reply_content = "⛔ ليس لديك صلاحية تسجيل المصاريف عبر واتساب من هذا الرقم."
		else:
			try:
				from hagag_erp.tax_engine import (
					calculate_zatca_tax,
					create_draft_journal_entry,
					get_company_tax_accounts
				)

				amount = parsed_expense["amount"]
				is_inclusive = parsed_expense["is_inclusive"]
				tax_calc = calculate_zatca_tax(amount, is_inclusive=is_inclusive)

				tax_accs = get_company_tax_accounts(company)
				expense_account = (hub.default_expense_account if hub and hub.default_expense_account else None) or tax_accs.get("default_expense_account")
				vat_account = (hub.default_vat_account if hub and hub.default_vat_account else None) or tax_accs.get("input_vat_account")
				credit_account = target_custody_account or tax_accs.get("default_cash_account")

				if not expense_account:
					expense_account = frappe.db.get_value("Account", {"company": company, "root_type": "Expense", "is_group": 0}, "name")
				if not vat_account:
					vat_account = frappe.db.get_value("Account", {"company": company, "account_type": "Tax", "is_group": 0}, "name")
				if not credit_account:
					credit_account = frappe.db.get_value("Account", {"company": company, "account_type": "Cash", "is_group": 0}, "name")

				if not (expense_account and vat_account and credit_account):
					raise ValueError("لم يتم تهيئة الحسابات المحاسبية المطلوبة (مصاريف/ضريبة/صندوق) بعد.")

				# Create balanced Draft Journal Entry (docstatus = 0)
				je_lines = [
					{
						"account": expense_account,
						"debit": float(tax_calc["net_amount"]),
						"credit": 0.0,
						"project": target_project,
						"cost_center": target_cost_center,
						"user_remark": f"مصروف عبر واتساب: {text[:140]}"
					},
					{
						"account": vat_account,
						"debit": float(tax_calc["tax_amount"]),
						"credit": 0.0,
						"project": target_project,
						"cost_center": target_cost_center,
						"user_remark": f"ضريبة القيمة المضافة 15% ZATCA: {text[:140]}"
					},
					{
						"account": credit_account,
						"debit": 0.0,
						"credit": float(tax_calc["total_amount"]),
						"project": target_project,
						"cost_center": target_cost_center,
						"user_remark": f"دفعة من صندوق/عهدة: {sender_name or sender_phone}"
					}
				]

				user_remark = f"مصروف عبر واتساب من Elsaidy WhatsApp Hub من {sender_name} ({sender_phone}).\nالرسالة الأصلية: {text}"
				jv = create_draft_journal_entry(
					company=company,
					accounts_data=je_lines,
					user_remark=user_remark,
					reference_id=f"WA-{msg_id}"
				)

				created_doc = jv
				log_doc.linked_document_type = "Journal Entry"
				log_doc.linked_document_name = jv.name
				log_doc.status = "Processed"

				doc_url = f"https://erp.elsaidy.org/app/journal-entry/{jv.name}"
				project_name = frappe.db.get_value("Project", target_project, "project_name") if target_project else "عام"

				reply_content = (
					f"✅ *تم تسجيل المصروف بنجاح (مسودة) ✅*\n"
					f"━━━━━━━━━━━━━━━━━━━\n"
					f"🔖 *رقم القيد:* `{jv.name}`\n"
					f"🏗️ *المشروع:* {project_name}\n"
					f"💵 *المبلغ الصافي:* {tax_calc['net_amount']:,.2f} ر.س\n"
					f"🏛️ *ضريبة القيمة المضافة (15%):* {tax_calc['tax_amount']:,.2f} ر.س\n"
					f"💰 *المجموع الإجمالي:* {tax_calc['total_amount']:,.2f} ر.س\n"
					f"👤 *المسجّل / العهدة:* {sender_name or sender_phone}\n"
					f"━━━━━━━━━━━━━━━━━━━\n"
					f"🔗 *رابط المستند للاعتماد:*\n{doc_url}"
				)

			except Exception as je_exc:
				frappe.log_error(f"WhatsApp Expense Creation Error: {str(je_exc)}", "Elsaidy WhatsApp Hub")
				log_doc.error_message = str(je_exc)
				log_doc.status = "Failed"
				reply_content = f"⚠️ حدث خطأ في تسجيل المصروف: {str(je_exc)}"

	# ── AI Reply Path ─────────────────────────────────────────────────────────
	elif enable_ai and ai_api_key and bot_mode != "Accounting Commands Only":
		log_doc.extracted_intent = "AI Chat Reply"
		try:
			reply_content = call_ai_api(
				user_message=text,
				provider=ai_provider,
				api_key=ai_api_key,
				model=ai_model,
				system_prompt=ai_system_prompt
			)
			log_doc.status = "Processed"
		except Exception as ai_err:
			frappe.log_error(f"AI Reply Error: {str(ai_err)}", "Elsaidy WhatsApp Hub")
			log_doc.status = "Failed"
			reply_content = f"عذراً، حدث خطأ في الذكاء الاصطناعي. [{str(ai_err)[:50]}]"

	# ── Balance Inquiry Path (fallback before generic help) ───────────────────
	else:
		log_doc.extracted_intent = "Inquiry / Chat"
		inquiry_keywords = ["رصيد", "الرصيد", "الميزانية", "ميزان", "كم في"]
		is_inquiry = any(kw in text for kw in inquiry_keywords)

		if is_inquiry and (not contact_rule or contact_rule.can_request_balance):
			# Query custody account balance
			if target_custody_account:
				balance = frappe.db.sql("""
					SELECT SUM(debit - credit) as balance
					FROM `tabGL Entry`
					WHERE account = %s AND is_cancelled = 0
				""", (target_custody_account,), as_dict=True)
				current_bal = flt(balance[0].balance) if balance and balance[0].balance else 0.0
				reply_content = (
					f"💰 *استعلام رصيد العهدة*\n"
					f"━━━━━━━━━━━━━━━━━━━\n"
					f"👤 *الاسم:* {sender_name or (contact_rule.contact_name if contact_rule else sender_phone)}\n"
					f"🏦 *حساب العهدة:* {target_custody_account}\n"
					f"💵 *الرصيد الحالي المتاح:* {current_bal:,.2f} ر.س\n"
					f"━━━━━━━━━━━━━━━━━━━\n"
					f"نظام Elsaidy ERP - دقيق وموثوق وآمن"
				)
			else:
				reply_content = "لا يوجد حساب عهدة مرتبط برقمك. تواصل مع المحاسب لإعداد الحساب."
		else:
			# Generic help message when no AI and no match
			help_mode_note = ""
			if bot_mode == "Accounting Commands Only":
				help_mode_note = "\n_(البوت يعمل حالياً في وضع الأوامر المحاسبية فقط)_"
			reply_content = (
				f"مرحباً {sender_name or ''} في *Elsaidy WhatsApp Hub* 👋\n"
				f"يمكنني مساعدتك في تسجيل المصاريف مباشرةً. أرسل مثلاً:\n"
				f"مثال: _صرفت 500 ريال وقود محطة الأمانة للمشروع_\n"
				f"وسيتم تسجيل القيد فوراً مع احتساب ضريبة ZATCA تلقائياً.{help_mode_note}"
			)

	# ── 6. Send Quoted WhatsApp Reply ─────────────────────────────────────────
	if reply_content and hub and hub.auto_reply_enabled:
		try:
			send_baileys_reply(reply_jid, reply_content, quoted_msg_id=msg_id)
			log_doc.status = "Replied"
		except Exception as reply_err:
			frappe.log_error(f"WhatsApp Reply Send Error: {str(reply_err)}", "Elsaidy WhatsApp Hub")

	# 7. Save Log
	elapsed_ms = (time.time() - start_time) * 1000.0
	log_doc.reply_text = reply_content
	log_doc.execution_time_ms = round(elapsed_ms, 2)
	log_doc.insert(ignore_permissions=True)
	frappe.db.commit()

	return {
		"status": "ok",
		"message_id": msg_id,
		"log": log_doc.name,
		"linked_doc": created_doc.name if created_doc else None,
		"execution_time_ms": log_doc.execution_time_ms
	}
