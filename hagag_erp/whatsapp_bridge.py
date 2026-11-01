# Copyright (c) 2026, Elsaidy ERP and contributors
# For license information, please see license.txt

import re
import time
import json
from decimal import Decimal
import requests
import frappe
from frappe import _
from frappe.utils import now_datetime, cint, flt, today

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
	
	api_token = "HAGAG_WA_7f3c9a2d6e4b8a1c"
	if hub and hasattr(hub, "get_password"):
		try:
			saved_token = hub.get_password("api_token", raise_exception=False)
			if saved_token:
				api_token = saved_token
		except Exception:
			pass

	url = f"{base_url}/{endpoint.lstrip('/')}"
	headers = {
		"Authorization": f"Bearer {api_token}",
		"x-api-token": api_token,
		"Content-Type": "application/json"
	}

	try:
		if method.upper() == "POST":
			resp = requests.post(url, json=data or {}, headers=headers, timeout=20)
		else:
			resp = requests.get(url, headers=headers, timeout=20)

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
# AI Provider Engine & Local Fallback
# ──────────────────────────────────────────────────────────────────────────────

def call_ai_api(user_message: str, provider: str, api_key: str, model: str, system_prompt: str) -> str:
	"""
	Calls AI API (Gemini or OpenAI-compatible) with strict error isolation and timeout.
	Falls back to local intelligent response if the provider is unavailable.
	"""
	if not api_key or not model:
		return generate_local_fallback_reply(user_message, "لم يتم تكوين مفتاح الذكاء الاصطناعي")

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
					"maxOutputTokens": 600,
					"temperature": 0.7
				}
			}
			resp = requests.post(url, json=payload, timeout=25)
			data = resp.json()

			if resp.status_code != 200:
				err = data.get("error", {}).get("message", str(resp.status_code))
				frappe.log_error(f"Gemini API Error: {err}", "Elsaidy WhatsApp Hub AI")
				return generate_local_fallback_reply(user_message, f"خطأ في الاتصال بالنموذج [{err[:40]}]")

			candidates = data.get("candidates", [])
			if not candidates:
				return generate_local_fallback_reply(user_message, "لم يقدم النموذج رداً")

			return (
				candidates[0]
				.get("content", {})
				.get("parts", [{}])[0]
				.get("text", "")
				.strip()
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
					{"role": "system", "content": system_prompt or "أنت المساعد الذكي لشركة الصعيدي للمقاولات."},
					{"role": "user", "content": user_message}
				],
				"max_tokens": 600,
				"temperature": 0.7
			}
			resp = requests.post(url, json=payload, headers=headers, timeout=25)
			data = resp.json()

			if resp.status_code != 200:
				err = data.get("error", {}).get("message", str(resp.status_code))
				frappe.log_error(f"OpenAI API Error: {err}", "Elsaidy WhatsApp Hub AI")
				return generate_local_fallback_reply(user_message, f"خطأ في الاتصال [{err[:40]}]")

			return data["choices"][0]["message"]["content"].strip()

		else:
			return generate_local_fallback_reply(user_message, f"المزود {provider} غير مدعوم")

	except requests.Timeout:
		frappe.log_error("AI API Timeout (>25s)", "Elsaidy WhatsApp Hub AI")
		return generate_local_fallback_reply(user_message, "تجاوز مهلة الاستجابة")
	except Exception as e:
		frappe.log_error(f"AI API Exception: {str(e)}", "Elsaidy WhatsApp Hub AI")
		return generate_local_fallback_reply(user_message, str(e))


def generate_local_fallback_reply(user_message: str, error_context: str = "") -> str:
	"""
	Local Rule-Based Fallback Engine.
	Guarantees that WhatsApp never fails to respond even if external AI APIs are down.
	"""
	norm = user_message.translate(ARABIC_TO_ASCII_DIGITS).lower()

	if any(kw in norm for kw in ["رصيد", "ميزانية", "فلوس", "عهدة"]):
		return (
			"💰 *المساعد المالي لشركة الصعيدي*\n"
			"━━━━━━━━━━━━━━━━━━━\n"
			"يمكنك معرفة رصيد عهدتك بكتابة:\n"
			"👉 *رصيد العهدة*\n"
			"وسيقوم النظام بالاستعلام المباشر من القيود المحاسبية."
		)

	if any(kw in norm for kw in ["صرف", "دفع", "شراء", "فاتورة"]):
		return (
			"📝 *تسجيل المصاريف اليومية*\n"
			"━━━━━━━━━━━━━━━━━━━\n"
			"أرسل المصروف بالصيغة:\n"
			"👉 *صرفت 500 ريال [البيان] لمشروع [اسم المشروع]*\n"
			"وسيتكفل النظام بحساب ضريبة القيمة المضافة 15% وإنشاء القيد كمسودة."
		)

	return (
		"مرحباً بك في *منظومة الصعيدي الذكية* 🏗️\n"
		"أنا المساعد الآلي لخدمتكم. يمكنك إرسال:\n"
		"• تسجيل المصاريف: _صرفت 300 ريال ديزل لموقع الرياض_\n"
		"• الاستعلام عن الرصيد: _رصيد العهدة_\n"
		"وسأقوم بخدمتك على الفور."
	)


# ──────────────────────────────────────────────────────────────────────────────
# Natural Language Parsing (ZATCA & ERP)
# ──────────────────────────────────────────────────────────────────────────────

def parse_expense_from_text(text: str) -> dict:
	"""
	Parses Arabic natural language expense messages for amount, VAT inclusiveness, description, and vendor.
	"""
	if not text:
		return None

	normalized_text = text.translate(ARABIC_TO_ASCII_DIGITS)

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

	# VAT inclusion determination
	is_inclusive = True
	if "قبل الضريبة" in normalized_text or "بدون ضريبة" in normalized_text or "غير شامل" in normalized_text:
		is_inclusive = False
	elif "شامل" in normalized_text or "مع الضريبة" in normalized_text:
		is_inclusive = True

	# Extract vendor if present
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
	"""Helper to send reply via Baileys API with strict destination validation."""
	clean_jid = (jid or "").strip()
	if not clean_jid:
		return {"status": "error", "reason": "Empty JID for reply"}

	# CRITICAL GUARD: Never reply to broadcast or newsletter
	if "@newsletter" in clean_jid or "@broadcast" in clean_jid or clean_jid == "status@broadcast":
		frappe.logger("whatsapp").warn(f"[SendBlocked] Refusing to reply to broadcast/newsletter: {clean_jid}")
		return {"status": "ignored", "reason": "Cannot reply to newsletter/broadcast"}

	hub = get_hub_settings()
	bot_phone = normalize_phone_number(hub.connected_phone or hub.bot_phone_number or "")
	if bot_phone and (bot_phone in clean_jid or clean_jid.startswith(bot_phone)):
		frappe.logger("whatsapp").warn(f"[SendBlocked] Refusing to reply to bot's own number: {clean_jid}")
		return {"status": "ignored", "reason": "Cannot reply to bot itself"}

	payload = {
		"jid": clean_jid,
		"message": text,
		"quoted_message_id": quoted_msg_id
	}
	return call_baileys_api("send-message", method="POST", data=payload)


# ──────────────────────────────────────────────────────────────────────────────
# Core Webhook Endpoint
# ──────────────────────────────────────────────────────────────────────────────

@frappe.whitelist(allow_guest=True)
def receive_baileys_event():
	"""
	Core Webhook Endpoint invoked by Baileys Node.js container on 'messages.upsert'.
	Enforces:
	1. API Token Authentication.
	2. Strict Idempotency on 'message_id'.
	3. Rule Verification for Direct Chat and Groups.
	4. Bot Mode Routing (AI + Accounting Hybrid / Accounting Only / AI Only / Disabled).
	5. ZATCA Tax Engine Integration (strictly Draft docstatus=0).
	6. Quoted WhatsApp response with ERPNext direct URL.
	7. Logging into 'Elsaidy WhatsApp Log'.
	"""
	start_time = time.time()
	req = frappe.request

	# 1. Authenticate Token
	auth_header = req.headers.get("Authorization", "")
	api_token_header = req.headers.get("x-api-token", "")
	hub = get_hub_settings()
	
	expected_token = "HAGAG_WA_7f3c9a2d6e4b8a1c"
	if hub and hasattr(hub, "get_password"):
		try:
			saved_token = hub.get_password("api_token", raise_exception=False)
			if saved_token:
				expected_token = saved_token
		except Exception:
			pass

	is_authed = (auth_header == f"Bearer {expected_token}") or (api_token_header == expected_token)
	if not is_authed:
		frappe.response["http_status_code"] = 401
		return {"error": "Unauthorized"}

	# Parse Payload
	try:
		payload = req.get_json() or {}
	except Exception:
		payload = {}

	event_type = payload.get("event_type") or payload.get("event")
	if event_type not in ("message", "messages.upsert"):
		return {"status": "ignored", "reason": "Not a message event"}

	data = payload if payload.get("message_id") else payload.get("data", payload)

	msg_id = data.get("message_id") or data.get("msg_id")
	if not msg_id:
		return {"status": "error", "reason": "Missing msg_id / message_id"}

	is_group = bool(data.get("is_group"))
	group_jid = data.get("remote_jid") if is_group else data.get("group_jid", "")
	sender_jid = data.get("sender_jid") or ""
	sender_lid = data.get("sender_lid") or ""
	sender_phone = normalize_phone_number(data.get("sender_phone") or "")
	sender_name = data.get("push_name") or data.get("sender_name") or ""
	text = (data.get("text") or "").strip()
	has_media = bool(data.get("has_media"))
	remote_jid = data.get("remote_jid") or ""
	reply_jid = remote_jid or data.get("reply_jid") or (group_jid if is_group else (f"{sender_phone}@s.whatsapp.net" if sender_phone else sender_jid))

	# LID resolution: if sender_phone is empty and LID matches owner/contact
	if not sender_phone and (sender_jid or sender_lid or remote_jid):
		lid_str = sender_lid or sender_jid or remote_jid
		if "251036744843464" in lid_str:
			sender_phone = "966569589664"

	# 2. Read Bot Mode & AI Settings
	bot_mode = (hub.bot_mode if hub and hub.bot_mode else "AI + Accounting Hybrid")
	enable_ai = cint(hub.enable_ai_reply if hub else 0)
	ai_provider = (hub.ai_provider if hub and hub.ai_provider else "Gemini")
	ai_api_key = None
	if hub and enable_ai and hasattr(hub, "get_password"):
		try:
			ai_api_key = hub.get_password("ai_api_key", raise_exception=False) or None
		except Exception:
			ai_api_key = None

	ai_model = (hub.ai_model if hub and hub.ai_model else "gemini-2.5-flash")
	ai_system_prompt = (
		hub.ai_system_prompt
		if hub and hub.ai_system_prompt
		else "أنت المساعد الذكي لشركة الصعيدي للمقاولات."
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

	# Create Log Doc
	log_doc = frappe.new_doc("Elsaidy WhatsApp Log")
	log_doc.message_id = msg_id
	log_doc.direction = "Incoming"
	log_doc.sender_phone = sender_phone
	log_doc.sender_name = sender_name
	log_doc.is_group = 1 if is_group else 0
	log_doc.group_jid = group_jid
	log_doc.message_text = text
	log_doc.status = "Received"

	# 4. Access Control Verification
	target_project = None
	target_cost_center = hub.default_cost_center if hub else None
	target_custody_account = None
	company = hub.default_company if (hub and hub.default_company) else "شركة ركن سبل الأفق للمقاولات"
	contact_rule = None
	group_rule = None

	if is_group:
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
		matching_contacts = []
		if hub:
			for c in hub.allowed_direct_contacts:
				if not c.is_active:
					continue
				c_norm = normalize_phone_number(c.phone_number)
				# 1. Match by phone number
				if sender_phone and c_norm == sender_phone:
					matching_contacts.append(c)
					break
				# 2. Match by JID / Phone in JID
				if sender_jid and (c_norm in sender_jid or c.phone_number in sender_jid):
					matching_contacts.append(c)
					break
				# 3. Match known owner LID
				if "251036744843464" in (sender_lid or sender_jid or remote_jid) and c_norm == "966569589664":
					matching_contacts.append(c)
					if not sender_phone:
						sender_phone = "966569589664"
						log_doc.sender_phone = sender_phone
					break

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
				log_doc.error_message = f"Unregistered direct sender: {sender_phone or sender_jid}"
				log_doc.insert(ignore_permissions=True)
				frappe.db.commit()
				return {"status": "rejected", "reason": "Unregistered contact"}

	# ── 5. Intent Detection & Routing ─────────────────────────────────────────
	reply_content = None
	created_doc = None

	if bot_mode == "Disabled / Log Only":
		log_doc.extracted_intent = "Disabled Mode - Log Only"
		log_doc.status = "Ignored"
		log_doc.insert(ignore_permissions=True)
		frappe.db.commit()
		return {"status": "ok", "message_id": msg_id, "log": log_doc.name, "mode": "disabled"}

	parsed_expense = parse_expense_from_text(text)

	# ZATCA Expense Path
	if parsed_expense and bot_mode != "AI Assistant Only":
		log_doc.extracted_intent = "Expense Record"

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

				# Create Draft Journal Entry
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

	# AI Reply Path
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
			reply_content = generate_local_fallback_reply(text, str(ai_err))

	# Balance Inquiry or Generic Help Path
	else:
		log_doc.extracted_intent = "Inquiry / Chat"
		inquiry_keywords = ["رصيد", "الرصيد", "الميزانية", "ميزان", "كم في"]
		is_inquiry = any(kw in text for kw in inquiry_keywords)

		if is_inquiry and (not contact_rule or contact_rule.can_request_balance):
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
			reply_content = generate_local_fallback_reply(text)

	# 6. Send Quoted WhatsApp Reply
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


# ──────────────────────────────────────────────────────────────────────────────
# GUI Whitelisted Management Endpoints & AI Simulator
# ──────────────────────────────────────────────────────────────────────────────

@frappe.whitelist()
def get_dashboard_telemetry() -> dict:
	"""
	Aggregates real-time telemetry from Baileys engine and ERPNext MariaDB logs.
	Powers the main Enterprise Dashboard cards.
	"""
	hub = get_hub_settings()
	health_data = call_baileys_api("health", method="GET", hub_doc=hub)
	status_data = call_baileys_api("status", method="GET", hub_doc=hub)

	today_date = today()

	# DB Metrics for today
	try:
		stats = frappe.db.sql("""
			SELECT 
				COUNT(*) as total_today,
				SUM(CASE WHEN direction = 'Incoming' THEN 1 ELSE 0 END) as incoming_today,
				SUM(CASE WHEN status = 'Replied' THEN 1 ELSE 0 END) as replied_today,
				SUM(CASE WHEN extracted_intent = 'AI Chat Reply' THEN 1 ELSE 0 END) as ai_replies_today,
				SUM(CASE WHEN extracted_intent = 'Expense Record' AND status = 'Processed' THEN 1 ELSE 0 END) as expenses_today,
				SUM(CASE WHEN status = 'Failed' THEN 1 ELSE 0 END) as failed_today
			FROM `tabElsaidy WhatsApp Log`
			WHERE DATE(creation) = %s
		""", (today_date,), as_dict=True)
		db_metrics = stats[0] if stats else {}
	except Exception:
		db_metrics = {}

	is_connected = bool(health_data.get("connected") or status_data.get("connected"))
	connected_phone = health_data.get("phone") or status_data.get("bot_phone") or (hub.connected_phone if hub else None)
	engine_state = health_data.get("engine_state") or status_data.get("engine_state") or ("CONNECTED" if is_connected else "DISCONNECTED")

	# Auto-sync Hub document connection state in MariaDB
	new_db_status = "Connected" if is_connected else ("Connecting" if engine_state == "CONNECTING" else "Disconnected")
	if hub and (hub.connection_status != new_db_status or (connected_phone and hub.connected_phone != connected_phone)):
		frappe.db.set_value("Elsaidy WhatsApp Hub", None, {
			"connection_status": new_db_status,
			"connected_phone": connected_phone or hub.connected_phone or "",
			"last_sync_time": now_datetime()
		}, update_modified=False)
		frappe.db.commit()

	return {
		"status": "ok",
		"engine_state": engine_state,
		"whatsapp_connected": is_connected,
		"connected_phone": connected_phone,
		"bot_name": health_data.get("bot_name") or status_data.get("bot_name") or "Elsaidy WhatsApp Hub",
		"has_qr": bool(health_data.get("has_qr") or status_data.get("has_qr")),
		"uptime_seconds": health_data.get("uptime_seconds") or status_data.get("uptime_seconds") or 0,
		"memory_mb": health_data.get("memory_mb") or {},
		"version": health_data.get("version") or "3.2.0-enterprise",
		"today_metrics": {
			"incoming": cint(db_metrics.get("incoming_today", 0)),
			"replied": cint(db_metrics.get("replied_today", 0)),
			"ai_replies": cint(db_metrics.get("ai_replies_today", 0)),
			"expenses_processed": cint(db_metrics.get("expenses_today", 0)),
			"failed": cint(db_metrics.get("failed_today", 0))
		}
	}


@frappe.whitelist()
def heal_baileys_session(target: str) -> dict:
	"""
	Whitelisted endpoint to trigger targeted Bad MAC / decrypt session repair.
	Never wipes creds.json or all keys.
	"""
	if not frappe.has_permission("Elsaidy WhatsApp Hub", "write"):
		frappe.throw(_("ليس لديك صلاحية لتنفيذ هذا الإجراء."))

	clean_target = (target or "").strip()
	if not clean_target:
		frappe.throw(_("يجب تحديد رقم الهاتف أو JID المستهدف للإصلاح."))

	hub = get_hub_settings()
	return call_baileys_api("heal-sessions", method="POST", data={"target": clean_target}, hub_doc=hub)


@frappe.whitelist()
def wipe_baileys_session() -> dict:
	"""Whitelisted endpoint to trigger a hard session wipe."""
	if not frappe.has_permission("Elsaidy WhatsApp Hub", "write"):
		frappe.throw(_("ليس لديك صلاحية لتنفيذ هذا الإجراء."))

	hub = get_hub_settings()
	res = call_baileys_api("wipe-session", method="POST", hub_doc=hub)
	try:
		frappe.db.set_value("Elsaidy WhatsApp Hub", None, {
			"connection_status": "Disconnected",
			"connected_phone": None,
			"last_sync_time": now_datetime()
		}, update_modified=False)
		frappe.db.commit()
	except Exception:
		pass
	return res


@frappe.whitelist()
def get_baileys_logs(limit: int = 100, level: str = "", search: str = "") -> dict:
	"""Fetches the in-memory log ring buffer from Baileys with filtering."""
	hub = get_hub_settings()
	clean_limit = min(cint(limit) or 100, 200)
	query_params = f"limit={clean_limit}"
	if level:
		query_params += f"&level={level}"
	if search:
		query_params += f"&search={requests.utils.quote(search)}"

	return call_baileys_api(f"logs?{query_params}", method="GET", hub_doc=hub)


@frappe.whitelist()
def send_test_whatsapp_message(recipient: str, message: str) -> dict:
	"""Whitelisted helper to send test message from Frappe GUI."""
	if not frappe.has_permission("Elsaidy WhatsApp Hub", "write"):
		frappe.throw(_("ليس لديك صلاحية لتنفيذ هذا الإجراء."))

	clean_recipient = (recipient or "").strip()
	if not clean_recipient:
		frappe.throw(_("الرجاء إدخال رقم هاتف المستلم الخارجي أو معرف المجموعة."))

	hub = get_hub_settings()
	bot_phone = normalize_phone_number(hub.connected_phone or hub.bot_phone_number or "")
	norm_recipient = normalize_phone_number(clean_recipient)

	# Safety: Block sending to bot's own number
	if bot_phone and norm_recipient and (bot_phone == norm_recipient or norm_recipient.endswith(bot_phone) or bot_phone.endswith(norm_recipient)):
		frappe.throw(_("⚠️ لا يمكن إرسال رسالة اختبارية إلى رقم البوت نفسه ({0}). الرجاء إدخال رقم هاتف خارجي للمعاينة.").format(bot_phone))

	if "@newsletter" in clean_recipient or "@broadcast" in clean_recipient:
		frappe.throw(_("غير مسموح بالإرسال إلى قنوات البث أو النشرات الإخبارية."))

	is_group = clean_recipient.endswith("@g.us")
	is_lid = clean_recipient.endswith("@lid")

	if is_group or is_lid:
		jid = clean_recipient
	else:
		if not norm_recipient:
			frappe.throw(_("رقم الهاتف غير صالح."))
		jid = f"{norm_recipient}@s.whatsapp.net"

	payload = {
		"jid": jid,
		"message": message
	}
	res = call_baileys_api("send-message", method="POST", data=payload)

	# Record in Elsaidy WhatsApp Log as Outgoing
	if res.get("status") == "ok":
		log_doc = frappe.new_doc("Elsaidy WhatsApp Log")
		log_doc.message_id = res.get("msg_id") or f"TEST-{frappe.generate_hash(length=8)}"
		log_doc.direction = "Outgoing"
		log_doc.sender_phone = bot_phone
		log_doc.receiver_phone = norm_recipient
		log_doc.receiver_jid = jid
		log_doc.message_text = message
		log_doc.status = "Replied"
		log_doc.insert(ignore_permissions=True)
		frappe.db.commit()

	return res


@frappe.whitelist()
def simulate_whatsapp_message(text: str, sender_phone: str = "966569589664") -> dict:
	"""
	AI & Natural Language Simulator (Dry Run Mode).
	Evaluates a message without committing any documents to the database.
	"""
	hub = get_hub_settings()
	clean_text = (text or "").strip()
	if not clean_text:
		return {"status": "error", "message": "نص الرسالة مطلوب للمحاكاة"}

	bot_mode = (hub.bot_mode if hub and hub.bot_mode else "AI + Accounting Hybrid")
	enable_ai = cint(hub.enable_ai_reply if hub else 0)
	ai_provider = (hub.ai_provider if hub and hub.ai_provider else "Gemini")
	ai_model = (hub.ai_model if hub and hub.ai_model else "gemini-2.5-flash")
	
	ai_api_key = None
	if hub and hasattr(hub, "get_password"):
		try:
			ai_api_key = hub.get_password("ai_api_key", raise_exception=False) or None
		except Exception:
			ai_api_key = None

	ai_system_prompt = hub.ai_system_prompt if hub else "أنت المساعد المالي لمنظومة الصعيدي."

	parsed_expense = parse_expense_from_text(clean_text)

	if parsed_expense and bot_mode != "AI Assistant Only":
		from hagag_erp.tax_engine import calculate_zatca_tax
		tax_calc = calculate_zatca_tax(parsed_expense["amount"], is_inclusive=parsed_expense["is_inclusive"])

		simulated_lines = [
			{"account": hub.default_expense_account or "مصاريف عامة", "debit": float(tax_calc["net_amount"]), "credit": 0.0},
			{"account": hub.default_vat_account or "ضريبة القيمة المضافة 15%", "debit": float(tax_calc["tax_amount"]), "credit": 0.0},
			{"account": "صندوق النقدية / العهدة", "debit": 0.0, "credit": float(tax_calc["total_amount"])}
		]

		simulated_reply = (
			f"✅ *تم تسجيل المصروف بنجاح (محاكاة تجريبية - Dry Run) ✅*\n"
			f"━━━━━━━━━━━━━━━━━━━\n"
			f"🔖 *رقم القيد المقترح:* `JV-SIMULATED-0001`\n"
			f"💵 *المبلغ الصافي:* {tax_calc['net_amount']:,.2f} ر.س\n"
			f"🏛️ *ضريبة القيمة المضافة (15%):* {tax_calc['tax_amount']:,.2f} ر.س\n"
			f"💰 *المجموع الإجمالي:* {tax_calc['total_amount']:,.2f} ر.س\n"
			f"👤 *المسجّل:* {sender_phone}\n"
			f"━━━━━━━━━━━━━━━━━━━\n"
			f"💡 *حالة العملية:* محاكاة ناجحة 100% دون تسجيل في قاعدة البيانات."
		)

		return {
			"status": "ok",
			"mode": "Dry Run Simulation",
			"detected_intent": "Expense Record (ZATCA 15%)",
			"parsed_entities": {
				"amount": float(parsed_expense["amount"]),
				"net_amount": float(tax_calc["net_amount"]),
				"tax_amount": float(tax_calc["tax_amount"]),
				"total_amount": float(tax_calc["total_amount"]),
				"is_inclusive": parsed_expense["is_inclusive"],
				"vendor": parsed_expense["vendor"] or "غير محدد"
			},
			"simulated_document": {
				"doctype": "Journal Entry",
				"docstatus": 0,
				"lines": simulated_lines
			},
			"simulated_reply": simulated_reply
		}

	elif enable_ai and ai_api_key and bot_mode != "Accounting Commands Only":
		simulated_ai_reply = call_ai_api(
			user_message=clean_text,
			provider=ai_provider,
			api_key=ai_api_key,
			model=ai_model,
			system_prompt=ai_system_prompt
		)
		return {
			"status": "ok",
			"mode": "Dry Run Simulation",
			"detected_intent": f"AI Chat ({ai_provider} - {ai_model})",
			"parsed_entities": {},
			"simulated_reply": simulated_ai_reply
		}

	else:
		fallback_reply = generate_local_fallback_reply(clean_text)
		return {
			"status": "ok",
			"mode": "Dry Run Simulation",
			"detected_intent": "General Chat / Local Fallback",
			"parsed_entities": {},
			"simulated_reply": fallback_reply
		}
