# Copyright (c) 2026, Elsaidy ERP and contributors
# For license information, please see license.txt

import re
import time
import json
import hmac
import hashlib
from datetime import datetime, timezone
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



def require_hub_permission(permission="read", admin=False):
	if frappe.session.user == "Guest" or not frappe.has_permission("Elsaidy WhatsApp Hub", permission):
		frappe.throw(_("ليس لديك صلاحية لتنفيذ هذا الإجراء."), frappe.PermissionError)
	if admin and "System Manager" not in frappe.get_roles():
		frappe.throw(_("هذا الإجراء متاح لمدير النظام فقط."), frappe.PermissionError)


def canonical_jid(value):
	return re.sub(r":\d+(?=@)", "", str(value or "").strip())


def conversation_identity(value, hub=None):
	value = canonical_jid(value)
	if value.endswith("@g.us"):
		return value
	if value.endswith("@lid"):
		for rule in (hub.allowed_direct_contacts if hub else []):
			lid = canonical_jid(getattr(rule, "whatsapp_lid", ""))
			if lid and not lid.endswith("@lid"):
				lid += "@lid"
			if lid == value:
				return normalize_phone_number(rule.phone_number)
		return value
	return normalize_phone_number(value.split("@")[0])


def delivery_status_for(code):
	try:
		return {0: "Failed", 1: "Pending", 2: "Sent", 3: "Delivered", 4: "Read", 5: "Read"}.get(int(code))
	except (ValueError, TypeError):
		return None


def send_accepted(result):
	return isinstance(result, dict) and result.get("status") == "ok" and bool(result.get("msg_id"))


def record_outgoing(result, jid, text, hub, intent, in_reply_to=None):
	if not send_accepted(result):
		raise RuntimeError("Baileys send was not accepted: " + str(result.get("error") or result.get("status")))
	message_id = result["msg_id"]
	if frappe.db.exists("Elsaidy WhatsApp Log", {"message_id": message_id}):
		return
	doc = frappe.new_doc("Elsaidy WhatsApp Log")
	doc.message_id = message_id
	doc.direction = "Outgoing"
	doc.sender_phone = normalize_phone_number(hub.connected_phone or hub.bot_phone_number or "")
	doc.receiver_jid = canonical_jid(result.get("jid") or jid)
	partner = conversation_identity(jid, hub)
	doc.receiver_phone = partner if "@" not in partner else ""
	doc.conversation_id = partner
	doc.is_group = int(jid.endswith("@g.us"))
	doc.group_jid = jid if doc.is_group else ""
	doc.reply_jid = jid
	doc.in_reply_to = in_reply_to
	doc.message_text = text
	doc.status = "Replied"
	doc.delivery_status = "Pending"
	doc.extracted_intent = intent
	doc.insert(ignore_permissions=True)
	# A fast receipt can arrive before the send API request finishes.
	pending = frappe.cache().get_value(f"wa_receipt_{message_id}")
	if pending is not None:
		apply_delivery_receipt(message_id, pending)


def apply_delivery_receipt(message_id, code):
	status = delivery_status_for(code)
	if not status or not message_id:
		return None
	# Serialize receipt ordering, including the cache-before-outgoing-insert race.
	with frappe.cache().lock(f"wa_receipt_lock_{message_id}", timeout=15, blocking_timeout=5):
		cached = frappe.cache().get_value(f"wa_receipt_{message_id}")
		if cached is not None and int(cached) >= int(code):
			code = int(cached)
			status = delivery_status_for(code)
		frappe.cache().set_value(f"wa_receipt_{message_id}", int(code), expires_in_sec=259200)
		frappe.db.sql("""
			UPDATE `tabElsaidy WhatsApp Log`
			SET delivery_status = %s
			WHERE message_id = %s AND direction = 'Outgoing'
			AND (delivery_status IN ('Pending', 'Failed')
			 OR (delivery_status = 'Sent' AND %s IN ('Delivered', 'Read'))
			 OR (delivery_status = 'Delivered' AND %s = 'Read'))
		""", (status, message_id, status, status))
		frappe.db.commit()
	return status


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

	api_token = None
	if hub and hasattr(hub, "get_password"):
		try:
			saved_token = hub.get_password("api_token", raise_exception=False)
			if saved_token:
				api_token = saved_token
		except Exception:
			pass

	if not api_token:
		return {"status": "error", "error": "Baileys API token is not configured"}

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
			result = resp.json()
		except ValueError:
			return {"status": "error", "http_status": resp.status_code, "error": "Invalid Baileys JSON response"}
		if not isinstance(result, dict):
			return {"status": "error", "error": "Invalid Baileys response shape"}
		if not resp.ok:
			return {"status": "error", "http_status": resp.status_code, "error": result.get("error") or result.get("message") or "Baileys request rejected"}
		return result
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

	if hub and (hub.connection_status != conn_status or hub.connected_phone != bot_phone):
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
				"is_active": 0,
				"auto_reply_in_group": 0,
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
	require_hub_permission("write", admin=True)
	return {"status": "disabled", "error": "Session unlink and wipe operations are disabled."}


# ──────────────────────────────────────────────────────────────────────────────
# AI Provider Engine & Local Fallback
# ──────────────────────────────────────────────────────────────────────────────

def call_ai_api(user_message: str, provider: str, api_key: str, model: str, system_prompt: str, result_metadata=None) -> str:
	"""
	Calls AI API (Gemini or OpenAI-compatible) with strict error isolation and timeout.
	Falls back to local intelligent response if the provider is unavailable.
	"""
	def fallback(message, context):
		if result_metadata is not None:
			result_metadata["fallback"] = True
		return generate_local_fallback_reply(message, context)

	if not api_key or not model:
		return fallback(user_message, "لم يتم تكوين مفتاح الذكاء الاصطناعي")

	clean_model = (model or "").strip()
	if provider == "Gemini":
		# Normalize model identifier if user typed display name
		model_map = {
			"gemini 3.5 flash lite": "gemini-3.5-flash-lite",
			"gemini 3.8 flash": "gemini-3.8-flash",
			"gemini 2.5 flash": "gemini-2.5-flash",
			"gemini-flash": "gemini-2.5-flash",
			"gemini flash": "gemini-2.5-flash"
		}
		clean_model = model_map.get(clean_model.lower(), clean_model)
		if not clean_model:
			clean_model = "gemini-2.5-flash"

	try:
		if provider == "Gemini":
			url = f"https://generativelanguage.googleapis.com/v1beta/models/{clean_model}:generateContent"
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
			resp = requests.post(url, json=payload, headers={"x-goog-api-key": api_key}, timeout=25)
			data = resp.json()

			if resp.status_code != 200:
				err = data.get("error", {}).get("message", str(resp.status_code))
				frappe.log_error(f"Gemini API Error: {err}", "Elsaidy WhatsApp Hub AI")
				return fallback(user_message, f"خطأ في الاتصال بالنموذج [{err[:40]}]")

			candidates = data.get("candidates", [])
			if not candidates:
				return fallback(user_message, "لم يقدم النموذج رداً")

			parts = candidates[0].get("content", {}).get("parts", [])
			answer = "\n".join(part.get("text", "") for part in parts if not part.get("thought")).strip()
			return answer or fallback(user_message, "لم يقدم النموذج نصاً قابلاً للإرسال")

		elif provider in ("OpenAI", "Custom API"):
			url = "https://api.openai.com/v1/chat/completions"
			headers = {
				"Authorization": f"Bearer {api_key}",
				"Content-Type": "application/json"
			}
			payload = {
				"model": clean_model or "gpt-4o-mini",
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
				return fallback(user_message, f"خطأ في الاتصال [{err[:40]}]")

			return data["choices"][0]["message"]["content"].strip()

		else:
			return fallback(user_message, f"المزود {provider} غير مدعوم")

	except requests.Timeout:
		frappe.log_error("AI API Timeout (>25s)", "Elsaidy WhatsApp Hub AI")
		return fallback(user_message, "تجاوز مهلة الاستجابة")
	except Exception as e:
		frappe.log_error(f"AI API Exception: {type(e).__name__}", "Elsaidy WhatsApp Hub AI")
		return fallback(user_message, "Provider request failed")


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


def resolve_destination_jid(target: str) -> str:
	"""Preserve explicit LIDs/groups; use exact configured mapping for Baileys 6.x."""
	clean = canonical_jid(target)
	if re.fullmatch(r"\d+@lid|\d+(?:-\d+)?@g\.us", clean):
		return clean
	if "@" in clean and not re.fullmatch(r"\d+@s\.whatsapp\.net", clean):
		return ""
	phone = normalize_phone_number(clean.split("@")[0])
	hub = get_hub_settings()
	for rule in (hub.allowed_direct_contacts if hub else []):
		if rule.is_active and normalize_phone_number(rule.phone_number) == phone:
			lid = canonical_jid(getattr(rule, "whatsapp_lid", ""))
			if lid and "@" not in lid:
				lid += "@lid"
			if re.fullmatch(r"\d+@lid", lid):
				return lid
	return f"{phone}@s.whatsapp.net" if re.fullmatch(r"\d{9,15}", phone) else ""


@frappe.whitelist()
def sync_all_contact_mappings_to_baileys() -> dict:
	require_hub_permission("write")
	"""Pushes all known Contact Rule LIDs to Baileys engine for local fast routing."""
	try:
		rules = frappe.db.sql("""
			SELECT phone_number, whatsapp_lid
			FROM `tabElsaidy WhatsApp Contact Rule`
			WHERE is_active = 1
			  AND whatsapp_lid IS NOT NULL AND whatsapp_lid != ''
		""", as_dict=True)
		mappings = []
		for r in rules:
			clean_pn = normalize_phone_number(r.get("phone_number"))
			clean_lid = (r.get("whatsapp_lid") or "").strip()
			if clean_pn and clean_lid:
				mappings.append({"phone": clean_pn, "lid": clean_lid})
		if mappings:
			res = call_baileys_api("sync-contact-mapping", method="POST", data={"mappings": mappings})
			return {"status": "ok", "synced_count": len(mappings), "baileys_res": res}
		return {"status": "ok", "synced_count": 0}
	except Exception as e:
		frappe.logger("whatsapp").warn(f"Failed to sync contact mappings to Baileys: {e}")
		return {"status": "error", "message": str(e)}


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
	if bot_phone and (bot_phone == conversation_identity(clean_jid, hub)):
		frappe.logger("whatsapp").warn(f"[SendBlocked] Refusing to reply to bot's own number: {clean_jid}")
		return {"status": "ignored", "reason": "Cannot reply to bot itself"}

	# Dynamic Outbound Identity Resolution (Auto-resolves to Cloud LID if available)
	target_jid = resolve_destination_jid(clean_jid)

	payload = {
		"jid": target_jid,
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
	Core Webhook Endpoint invoked by Baileys Node.js container:
	1. Real-time delivery status updates ('status_update' / 'messages.update').
	2. Inbound messages ('message' / 'messages.upsert').
	3. Dynamic Identity Resolution & Auto-Learning (LID <-> Phone).
	4. Human Takeover Check (suppress bot auto-reply when human takeover active).
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

	expected_token = None
	if hub and hasattr(hub, "get_password"):
		try:
			saved_token = hub.get_password("api_token", raise_exception=False)
			if saved_token:
				expected_token = saved_token
		except Exception:
			pass

	is_authed = bool(expected_token) and (hmac.compare_digest(auth_header, f"Bearer {expected_token}") or hmac.compare_digest(api_token_header, expected_token))
	if not is_authed:
		frappe.response["http_status_code"] = 401
		return {"error": "Unauthorized"}

	# Parse Payload
	try:
		payload = req.get_json() or {}
	except Exception:
		payload = {}

	event_type = payload.get("event_type") or payload.get("event")

	# ── 1.1 Handle Delivery Status Updates ────────────────────────────────────
	if event_type in ("status_update", "messages.update"):
		msg_id = payload.get("message_id")
		raw_status = payload.get("status_code", payload.get("status"))
		delivery_status = apply_delivery_receipt(msg_id, raw_status)
		return {"status": "ok", "event_type": "status_update", "message_id": msg_id, "delivery_status": delivery_status}

	if event_type not in ("message", "messages.upsert"):
		return {"status": "ignored", "reason": f"Unhandled event type: {event_type}"}

	data = payload if payload.get("message_id") else payload.get("data", payload)
	if not isinstance(data, dict) or not data.get("message_id") or not data.get("remote_jid"):
		frappe.response["http_status_code"] = 400
		return {"status": "error", "error": "Missing message identity"}
	message_id = data["message_id"]
	# Durable inbox admission precedes acknowledgement; a failed enqueue is retryable.
	with frappe.cache().lock(f"wa_inbound_{hashlib.sha256(message_id.encode()).hexdigest()}", timeout=30, blocking_timeout=5):
		existing = frappe.db.get_value("Elsaidy WhatsApp Log", {"message_id": message_id}, ["name", "status"], as_dict=True)
		if not existing:
			doc = frappe.new_doc("Elsaidy WhatsApp Log")
			doc.message_id = message_id
			doc.direction = "Incoming"
			doc.status = "Received"
			doc.delivery_status = "Delivered"
			doc.message_text = data.get("text") or ""
			doc.sender_phone = normalize_phone_number(data.get("sender_phone") or "")
			doc.sender_lid = canonical_jid(data.get("sender_lid"))
			doc.sender_name = data.get("push_name") or ""
			doc.is_group = int(bool(data.get("is_group")))
			doc.group_jid = data["remote_jid"] if doc.is_group else ""
			doc.reply_jid = data["remote_jid"]
			doc.conversation_id = conversation_identity(doc.group_jid or doc.sender_phone or doc.sender_lid or doc.reply_jid, hub)
			doc.inbound_payload = json.dumps(data)
			doc.insert(ignore_permissions=True)
			frappe.db.commit()
		elif existing.status != "Received":
			return {"status": "already_processed", "message_id": message_id}
		frappe.enqueue("hagag_erp.whatsapp_bridge.process_baileys_message", queue="short", timeout=180, message_id=message_id)
	return {"status": "queued", "message_id": message_id}


def process_baileys_message(message_id):
	"""Workers serialize one message. Processing/Failed records require operator review, never blind replay."""
	with frappe.cache().lock(f"wa_process_{hashlib.sha256(message_id.encode()).hexdigest()}", timeout=240, blocking_timeout=5):
		doc = frappe.get_doc("Elsaidy WhatsApp Log", {"message_id": message_id})
		if doc.status != "Received":
			return
		doc.status = "Processing"
		doc.save(ignore_permissions=True)
		frappe.db.commit()
		try:
			return _process_baileys_payload(json.loads(doc.inbound_payload), doc)
		except Exception:
			frappe.db.rollback()
			doc.reload()
			doc.status = "Failed"
			doc.error_message = "Background processing failed; inspect Frappe Error Log before retrying."
			doc.save(ignore_permissions=True)
			frappe.db.commit()
			frappe.log_error(title="WhatsApp background processing failed", message=frappe.get_traceback())
			raise


def enqueue_pending_whatsapp_messages():
	for row in frappe.get_all("Elsaidy WhatsApp Log", filters={"direction": "Incoming", "status": "Received", "inbound_payload": ["is", "set"]}, fields=["message_id"], limit_page_length=100):
		frappe.enqueue("hagag_erp.whatsapp_bridge.process_baileys_message", queue="short", timeout=180, message_id=row.message_id)


def _process_baileys_payload(data, log_doc):
	start_time = time.time()
	hub = get_hub_settings()
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

	log_doc.message_id = msg_id
	log_doc.direction = "Incoming"
	log_doc.sender_phone = sender_phone
	log_doc.sender_name = sender_name
	log_doc.sender_lid = sender_lid
	log_doc.is_group = 1 if is_group else 0
	log_doc.group_jid = group_jid
	log_doc.reply_jid = reply_jid
	log_doc.message_text = text
	log_doc.status = "Processing"
	log_doc.delivery_status = "Delivered"
	log_doc.conversation_id = conversation_identity(group_jid or sender_phone or sender_lid or reply_jid, hub)
	if data.get("timestamp"):
		log_doc.whatsapp_timestamp = datetime.fromtimestamp(float(data["timestamp"]), timezone.utc).replace(tzinfo=None)

	# 4. Access Control Verification & Dynamic Identity Resolution
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
				if bot_phone and f"{normalize_phone_number(bot_phone)}@s.whatsapp.net" not in [canonical_jid(j) for j in data.get("mentioned_jids", [])]:
					log_doc.status = "Ignored"
					log_doc.error_message = "Group message ignored (require_mention active and bot not tagged)"
					log_doc.save(ignore_permissions=True)
					frappe.db.commit()
					return {"status": "ignored", "reason": "No mention"}
		else:
			if not (hub and hub.allow_unregistered_groups):
				log_doc.status = "Ignored"
				log_doc.error_message = f"Unregistered group: {group_jid}"
				log_doc.save(ignore_permissions=True)
				frappe.db.commit()
				return {"status": "ignored", "reason": "Unregistered group"}
	else:
		# Dynamic Contact Matching without hardcoded rules
		matching_contacts = []
		if hub:
			for c in hub.allowed_direct_contacts:
				if not c.is_active:
					continue
				c_norm = normalize_phone_number(c.phone_number)
				c_lid = getattr(c, "whatsapp_lid", "") or ""

				# 1. Match by WhatsApp Cloud LID
				if c_lid and sender_lid and canonical_jid(c_lid if "@" in c_lid else c_lid + "@lid") == canonical_jid(sender_lid):
					matching_contacts.append(c)
					if not sender_phone and c_norm:
						sender_phone = c_norm
						log_doc.sender_phone = sender_phone
					break

				# 2. Match by Normalized Phone
				if sender_phone and c_norm == sender_phone:
					matching_contacts.append(c)
					break

				# 3. Match by JID match
				if c_norm and sender_jid.endswith("@s.whatsapp.net") and c_norm == normalize_phone_number(canonical_jid(sender_jid).split("@")[0]):
					matching_contacts.append(c)
					if not sender_phone and c_norm:
						sender_phone = c_norm
						log_doc.sender_phone = sender_phone
					break

		if matching_contacts:
			contact_rule = matching_contacts[0]
			target_project = contact_rule.default_project
			target_cost_center = contact_rule.default_cost_center or target_cost_center
			target_custody_account = contact_rule.default_custody_account

			# DYNAMIC AUTO-LEARNING: If contact matched by phone and contact rule has no LID, auto-save sender_lid!
			c_lid = getattr(contact_rule, "whatsapp_lid", "") or ""
			if sender_lid and not c_lid:
				try:
					frappe.db.set_value("Elsaidy WhatsApp Contact Rule", contact_rule.name, "whatsapp_lid", sender_lid, update_modified=False)
					frappe.db.commit()
					# Push mapping to Baileys engine
					call_baileys_api("sync-contact-mapping", method="POST", data={
						"mappings": [{"lid": sender_lid, "phone": normalize_phone_number(contact_rule.phone_number)}]
					})
				except Exception as map_err:
					frappe.logger("whatsapp").warn(f"Failed to auto-save LID to contact rule: {map_err}")

		else:
			if not (hub and hub.allow_unregistered_direct):
				unregistered_msg = hub.unregistered_auto_reply if (hub and hub.unregistered_auto_reply) else (
					"عذراً، لست مرخصاً للتفاعل مع بوت Elsaidy ERP. تواصل معنا من خلال القنوات الرسمية."
				)
				if hub and hub.auto_reply_enabled:
					result = send_baileys_reply(reply_jid, unregistered_msg, quoted_msg_id=msg_id)
					if send_accepted(result):
						record_outgoing(result, reply_jid, unregistered_msg, hub, "Authorization rejection", msg_id)
					else:
						log_doc.error_message = "Authorization reply was not accepted"

				log_doc.status = "Ignored"
				log_doc.reply_text = unregistered_msg
				log_doc.error_message = f"Unregistered direct sender: {sender_phone or sender_jid or sender_lid}"
				log_doc.save(ignore_permissions=True)
				frappe.db.commit()
				return {"status": "rejected", "reason": "Unregistered contact"}

	# ── 4.1 Check Human Takeover Active ───────────────────────────────────────
	is_takeover = False
	if log_doc.conversation_id:
		try:
			is_takeover = bool(frappe.cache().get_value(f"wa_takeover_{log_doc.conversation_id}"))
		except Exception:
			is_takeover = False

	if is_takeover:
		log_doc.extracted_intent = "Human Takeover Active"
		log_doc.status = "Processed"
		log_doc.reply_text = None
		log_doc.save(ignore_permissions=True)
		frappe.db.commit()
		return {
			"status": "ok",
			"message_id": msg_id,
			"human_takeover": True,
			"log": log_doc.name,
			"message": "Message logged. Automated reply suppressed (Human takeover mode active)."
		}

	# ── 5. Intent Detection & Routing ─────────────────────────────────────────
	reply_content = None
	created_doc = None

	if bot_mode == "Disabled / Log Only":
		log_doc.extracted_intent = "Disabled Mode - Log Only"
		log_doc.status = "Ignored"
		log_doc.save(ignore_permissions=True)
		frappe.db.commit()
		return {"status": "ok", "message_id": msg_id, "log": log_doc.name, "mode": "disabled"}

	parsed_expense = parse_expense_from_text(text)

	# ZATCA Expense Path
	if parsed_expense and bot_mode != "AI Assistant Only":
		log_doc.extracted_intent = "Expense Record"

		if not contact_rule or not contact_rule.can_record_expenses:
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

				# Create Draft Journal Entry (docstatus=0 strictly)
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
			ai_metadata = {}
			reply_content = call_ai_api(
				user_message=text,
				provider=ai_provider,
				api_key=ai_api_key,
				model=ai_model,
				system_prompt=ai_system_prompt,
				result_metadata=ai_metadata
			)
			if ai_metadata.get("fallback"):
				log_doc.extracted_intent = "AI Fallback Reply"
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
	if reply_content and hub and hub.auto_reply_enabled and (not is_group or (group_rule and group_rule.auto_reply_in_group)):
		try:
			send_result = send_baileys_reply(reply_jid, reply_content, quoted_msg_id=msg_id)
			if send_result.get("status") != "ok" or not send_result.get("msg_id"):
				raise RuntimeError(f"Baileys send was not accepted: {send_result.get('error') or send_result.get('reason') or send_result.get('status')}")
			log_doc.status = "Replied"
			record_outgoing(send_result, reply_jid, reply_content, hub, log_doc.extracted_intent, msg_id)
		except Exception as reply_err:
			log_doc.status = "Failed"
			log_doc.error_message = "Reply not accepted; delivery is unconfirmed."
			log_doc.error_message = str(reply_err)[:1000]
			frappe.logger("whatsapp").error(f"WhatsApp Reply Send Error: {reply_err}")

	# 7. Save Log
	if log_doc.status == "Processing":
		log_doc.status = "Processed"
	elapsed_ms = (time.time() - start_time) * 1000.0
	log_doc.reply_text = reply_content
	log_doc.execution_time_ms = round(elapsed_ms, 2)
	log_doc.save(ignore_permissions=True)
	frappe.db.commit()

	return {
		"status": "ok",
		"message_id": msg_id,
		"log": log_doc.name,
		"linked_doc": created_doc.name if created_doc else None,
		"execution_time_ms": log_doc.execution_time_ms
	}


# ──────────────────────────────────────────────────────────────────────────────
# GUI Whitelisted Management Endpoints, Telemetry & Message Center
# ──────────────────────────────────────────────────────────────────────────────

@frappe.whitelist()
def get_dashboard_telemetry() -> dict:
	require_hub_permission("read")
	"""
	Aggregates real-time telemetry from Baileys engine and ERPNext MariaDB logs.
	Strictly read-only during polling to prevent database locks.
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
				SUM(CASE WHEN direction = 'Outgoing' THEN 1 ELSE 0 END) as replied_today,
				SUM(CASE WHEN direction = 'Outgoing' AND extracted_intent = 'AI Chat Reply' THEN 1 ELSE 0 END) as ai_replies_today,
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

	# Safe auto-sync Hub state only when change is detected
	new_db_status = "Connected" if is_connected else ("Connecting" if engine_state == "CONNECTING" else "Disconnected")
	if hub and (hub.connection_status != new_db_status or (connected_phone and hub.connected_phone != connected_phone)):
		try:
			frappe.db.set_value("Elsaidy WhatsApp Hub", None, {
				"connection_status": new_db_status,
				"connected_phone": connected_phone or hub.connected_phone or "",
				"last_sync_time": now_datetime()
			}, update_modified=False)
			frappe.db.commit()
		except Exception:
			pass

	return {
		"status": "ok",
		"engine_state": engine_state,
		"whatsapp_connected": is_connected,
		"connected_phone": connected_phone,
		"bot_name": health_data.get("bot_name") or status_data.get("bot_name") or "Elsaidy WhatsApp Hub",
		"has_qr": bool(health_data.get("has_qr") or status_data.get("has_qr")),
		"uptime_seconds": health_data.get("uptime_seconds") or status_data.get("uptime_seconds") or 0,
		"memory_mb": health_data.get("memory_mb") or {},
		"version": health_data.get("version") or "Unknown",
		"transport_metrics": health_data.get("metrics") or {},
		"telemetry_available": health_data.get("status") == "ok",
		"today_metrics": {
			"incoming": cint(db_metrics.get("incoming_today", 0)),
			"replied": cint(db_metrics.get("replied_today", 0)),
			"ai_replies": cint(db_metrics.get("ai_replies_today", 0)),
			"expenses_processed": cint(db_metrics.get("expenses_today", 0)),
			"failed": cint(db_metrics.get("failed_today", 0))
		}
	}


@frappe.whitelist()
def get_message_center_conversations(search: str = "", limit: int = 25, page: int = 1, conversation_filter: str = "all") -> dict:
	require_hub_permission("read")
	"""
	Fetches aggregated conversation threads for the Enterprise Message Center Inbox.
	"""
	limit = max(1, min(cint(limit) or 25, 100))
	offset = (max(cint(page), 1) - 1) * limit

	search_clause = ""
	args = []
	if search:
		search_term = f"%{search}%"
		search_clause = "WHERE (sender_phone LIKE %s OR receiver_phone LIKE %s OR sender_name LIKE %s OR message_text LIKE %s OR group_name LIKE %s)"
		args.extend([search_term, search_term, search_term, search_term, search_term])

	sql = f"""
		SELECT
			name, message_id, direction, sender_phone, receiver_phone, sender_name, receiver_jid,
			is_group, group_jid, group_name, status, delivery_status, extracted_intent,
			message_text, reply_text, creation,
			COALESCE(NULLIF(conversation_id, ''), CASE
				WHEN is_group = 1 THEN group_jid
				WHEN direction = 'Incoming' AND sender_phone IS NOT NULL AND sender_phone != '' THEN sender_phone
				WHEN direction = 'Outgoing' AND receiver_phone IS NOT NULL AND receiver_phone != '' THEN receiver_phone
				ELSE COALESCE(NULLIF(sender_lid, ''), NULLIF(reply_jid, ''), 'Unknown')
			END) AS conv_partner
		FROM `tabElsaidy WhatsApp Log`
		{search_clause}
		ORDER BY creation DESC
	"""
	logs = frappe.db.sql(sql, tuple(args), as_dict=True)

	conversations = {}
	hub = get_hub_settings()
	contact_rules_map = {}
	if hub:
		for c in hub.allowed_direct_contacts:
			norm = normalize_phone_number(c.phone_number)
			if norm:
				contact_rules_map[norm] = c

	for row in logs:
		partner = row.conv_partner
		if not row.is_group and row.direction == "Outgoing" and row.receiver_jid:
			partner = conversation_identity(row.receiver_jid, hub)
		elif not row.is_group and partner:
			partner = conversation_identity(partner, hub)
		if not partner or partner == 'Unknown':
			continue
		if hub and not row.is_group and partner == normalize_phone_number(hub.connected_phone or hub.bot_phone_number or ""):
			continue
		if partner not in conversations:
			is_takeover = False
			if not row.is_group:
				try:
					is_takeover = bool(frappe.cache().get_value(f"wa_takeover_{partner}"))
				except Exception:
					is_takeover = False

			contact_name = row.sender_name or partner
			if partner in contact_rules_map:
				contact_name = contact_rules_map[partner].contact_name
			elif row.is_group and row.group_name:
				contact_name = row.group_name

			conversations[partner] = {
				"partner_id": partner,
				"contact_name": contact_name,
				"is_group": bool(row.is_group),
				"group_name": row.group_name or "",
				"last_message": row.message_text or row.reply_text or "",
				"last_time": str(row.creation),
				"last_direction": row.direction,
				"last_status": row.status,
				"delivery_status": row.delivery_status or "Sent",
				"human_takeover": is_takeover,
				"message_count": 0
			}
		conversations[partner]["message_count"] += 1

	conv_list = list(conversations.values())
	if conversation_filter == "groups":
		conv_list = [c for c in conv_list if c["is_group"]]
	elif conversation_filter == "direct":
		conv_list = [c for c in conv_list if not c["is_group"]]
	elif conversation_filter == "failed":
		conv_list = [c for c in conv_list if c["last_status"] == "Failed" or c["delivery_status"] == "Failed"]
	elif conversation_filter == "takeover":
		conv_list = [c for c in conv_list if c["human_takeover"]]
	total = len(conv_list)
	paged_list = conv_list[offset:offset + limit]

	return {
		"status": "ok",
		"total": total,
		"page": page,
		"conversations": paged_list
	}


@frappe.whitelist()
def get_conversation_thread(target_id: str, limit: int = 50) -> dict:
	require_hub_permission("read")
	"""
	Fetches the chronological message thread for a given contact phone or group JID.
	"""
	clean_id = (target_id or "").strip()
	if not clean_id:
		return {"status": "error", "message": "Target ID required"}

	limit = max(1, min(cint(limit) or 50, 150))
	norm = conversation_identity(clean_id, get_hub_settings())

	logs = frappe.db.sql("""
		SELECT
			name, message_id, direction, sender_phone, receiver_phone, sender_name,
			is_group, group_jid, group_name, status, delivery_status, extracted_intent,
			linked_document_type, linked_document_name, execution_time_ms,
			message_text, reply_text, creation, whatsapp_timestamp
		FROM `tabElsaidy WhatsApp Log`
		WHERE (is_group = 1 AND group_jid = %s AND %s = 1)
		   OR (COALESCE(is_group, 0) = 0 AND %s = 0 AND (
		       conversation_id = %s OR sender_phone = %s OR receiver_phone = %s
		       OR sender_lid = %s OR receiver_jid = %s OR reply_jid = %s
		   ))
		ORDER BY creation DESC
		LIMIT %s
	""", (clean_id, int(clean_id.endswith("@g.us")), int(clean_id.endswith("@g.us")),
		norm, norm, norm, clean_id, clean_id, resolve_destination_jid(clean_id), limit), as_dict=True)

	is_takeover = False
	try:
		is_takeover = bool(frappe.cache().get_value(f"wa_takeover_{norm or clean_id}"))
	except Exception:
		is_takeover = False

	return {
		"status": "ok",
		"target_id": clean_id,
		"human_takeover": is_takeover,
		"messages": list(reversed(logs))
	}


@frappe.whitelist()
def send_conversation_reply(target_id: str, message: str, quoted_msg_id: str = None) -> dict:
	require_hub_permission("write")
	"""
	Sends an outbound reply in the Message Center conversation thread.
	"""
	if not frappe.has_permission("Elsaidy WhatsApp Hub", "write"):
		frappe.throw(_("ليس لديك صلاحية لتنفيذ هذا الإجراء."))

	clean_target = (target_id or "").strip()
	text = (message or "").strip()
	if not clean_target or not text:
		frappe.throw(_("الهدف والرسالة كلاهما مطلوب."))

	hub = get_hub_settings()
	bot_phone = normalize_phone_number(hub.connected_phone or hub.bot_phone_number or "")
	norm_target = normalize_phone_number(clean_target)

	# Safety checks
	if bot_phone and norm_target and (bot_phone == norm_target or norm_target.endswith(bot_phone)):
		frappe.throw(_("لا يمكن الإرسال إلى رقم البوت نفسه."))

	is_group = clean_target.endswith("@g.us")
	is_lid = clean_target.endswith("@lid")
	jid = clean_target if (is_group or is_lid) else resolve_destination_jid(clean_target)

	payload = {
		"jid": jid,
		"message": text,
		"quoted_message_id": quoted_msg_id
	}
	res = call_baileys_api("send-message", method="POST", data=payload)

	if send_accepted(res):
		record_outgoing(res, jid, text, hub, "Human Direct Reply", quoted_msg_id)
		frappe.db.commit()
		return {"status": "ok", "msg_id": res["msg_id"]}
	if res.get("status") == "ok":
		return {"status": "error", "error": "Baileys did not return a message ID"}

	return res


@frappe.whitelist()
def toggle_human_takeover(phone_number: str, enabled: int = 1, duration_minutes: int = 120) -> dict:
	require_hub_permission("write")
	"""
	Enables or disables Human Takeover mode for a phone number.
	When enabled, automated bot responses are suspended for this conversation.
	"""
	if not frappe.has_permission("Elsaidy WhatsApp Hub", "write"):
		frappe.throw(_("ليس لديك صلاحية لتنفيذ هذا الإجراء."))

	clean_phone = conversation_identity(phone_number, get_hub_settings())
	if not clean_phone:
		frappe.throw(_("رقم الهاتف غير صالح."))

	cache_key = f"wa_takeover_{clean_phone}"
	enabled_bool = bool(cint(enabled))

	if enabled_bool:
		duration_sec = min(max(cint(duration_minutes), 5), 1440) * 60
		frappe.cache().set_value(cache_key, 1, expires_in_sec=duration_sec)
		msg = f"تم تفعيل وضع التدخل البشري للرقم {clean_phone} لمدة {duration_minutes} دقيقة. البوت لن يرد تلقائياً."
	else:
		frappe.cache().delete_value(cache_key)
		msg = f"تم إلغاء وضع التدخل البشري للرقم {clean_phone}. البوت سيعود للرد التلقائي."

	return {
		"status": "ok",
		"phone_number": clean_phone,
		"human_takeover": enabled_bool,
		"message": msg
	}


@frappe.whitelist()
def test_ai_configuration(prompt: str = None) -> dict:
	require_hub_permission("write")
	"""
	Tests the configured AI engine with real round-trip latency measurement.
	"""
	if not frappe.has_permission("Elsaidy WhatsApp Hub", "write"):
		frappe.throw(_("ليس لديك صلاحية لتنفيذ هذا الإجراء."))

	hub = get_hub_settings()
	provider = hub.ai_provider if hub else "Gemini"
	model = hub.ai_model if hub else "gemini-2.5-flash"
	test_prompt = prompt or "السلام عليكم، ما هي الخدمات والمشاريع التي تقدمها شركة الصعيدي؟"

	ai_api_key = None
	if hub and hasattr(hub, "get_password"):
		try:
			ai_api_key = hub.get_password("ai_api_key", raise_exception=False) or None
		except Exception:
			ai_api_key = None

	system_prompt = hub.ai_system_prompt if hub else "أنت المساعد الذكي لشركة الصعيدي للمقاولات."

	t0 = time.time()
	ai_metadata = {}
	reply = call_ai_api(
		user_message=test_prompt,
		provider=provider,
		api_key=ai_api_key,
		model=model,
		system_prompt=system_prompt,
		result_metadata=ai_metadata
	)
	latency_ms = round((time.time() - t0) * 1000.0, 2)

	return {
		"status": "fallback" if ai_metadata.get("fallback") else "ok",
		"fallback_used": bool(ai_metadata.get("fallback")),
		"message": "AI provider unavailable; local fallback was used." if ai_metadata.get("fallback") else "Provider replied",
		"provider": provider,
		"model": model,
		"prompt": test_prompt,
		"reply": reply,
		"latency_ms": latency_ms,
		"has_api_key": bool(ai_api_key)
	}


@frappe.whitelist()
def get_system_health_report() -> dict:
	require_hub_permission("read")
	"""
	Generates comprehensive system health status covering Docker, Baileys, Database, and Webhook.
	"""
	hub = get_hub_settings()
	baileys_health = call_baileys_api("health", method="GET", hub_doc=hub)
	baileys_status = call_baileys_api("status", method="GET", hub_doc=hub)
	diagnostics = call_baileys_api("diagnostics", hub_doc=hub)

	# DB checks
	try:
		db_ok = True
		log_count = frappe.db.count("Elsaidy WhatsApp Log")
		contact_count = len(hub.allowed_direct_contacts) if hub else 0
		group_count = len(hub.allowed_groups) if hub else 0
	except Exception:
		db_ok = False
		log_count = 0
		contact_count = 0
		group_count = 0

	return {
		"status": "ok",
		"timestamp": str(now_datetime()),
		"server_diagnostics": diagnostics,
		"baileys": {
			"reachable": baileys_health.get("status") == "ok",
			"engine_state": baileys_status.get("engine_state") or baileys_health.get("engine_state") or "UNKNOWN",
			"connected": bool(baileys_status.get("connected") or baileys_health.get("connected")),
			"phone": baileys_status.get("bot_phone") or baileys_health.get("phone") or "",
			"bot_name": baileys_status.get("bot_name") or baileys_health.get("bot_name") or "",
			"uptime_seconds": baileys_status.get("uptime_seconds") or baileys_health.get("uptime_seconds") or 0,
			"memory_mb": baileys_health.get("memory_mb") or {},
			"version": baileys_health.get("version") or "3.2.0-enterprise"
		},
		"erpnext": {
			"db_connected": db_ok,
			"site": "erp.local",
			"hub_connection_status": hub.connection_status if hub else "Unknown",
			"total_logs": log_count,
			"active_contacts": contact_count,
			"active_groups": group_count,
			"bot_mode": hub.bot_mode if hub else "Unknown",
			"auto_reply_enabled": bool(hub.auto_reply_enabled if hub else False),
			"enable_ai_reply": bool(hub.enable_ai_reply if hub else False),
			"ai_provider": hub.ai_provider if hub else "Gemini",
			"ai_model": hub.ai_model if hub else "gemini-2.5-flash"
		}
	}


@frappe.whitelist()
def heal_baileys_session(target: str) -> dict:
	require_hub_permission("read")
	return {"status": "disabled", "error": "Signal key deletion is disabled. Inspect session diagnostics and logs."}


@frappe.whitelist()
def wipe_baileys_session() -> dict:
	require_hub_permission("write", admin=True)
	return {"status": "disabled", "error": "Session destruction is disabled."}


@frappe.whitelist()
def get_baileys_logs(limit: int = 100, level: str = "", search: str = "") -> dict:
	require_hub_permission("read")
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
def get_frappe_whatsapp_logs(limit: int = 50, search: str = "") -> dict:
	require_hub_permission("read")
	# Expose summaries and links; raw tracebacks may include confidential request data.
	rows = frappe.get_list("Error Log", filters={"method": ["like", "%WhatsApp%"]},
		fields=["name", "method", "creation"], order_by="creation desc",
		limit_page_length=max(1, min(cint(limit) or 50, 100)))
	if search:
		rows = [r for r in rows if search.lower() in (r.method or "").lower()]
	return {"status": "ok", "logs": rows}


@frappe.whitelist()
def send_test_whatsapp_message(recipient: str, message: str) -> dict:
	require_hub_permission("write")
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
	jid = clean_recipient if (is_group or is_lid) else resolve_destination_jid(clean_recipient)

	payload = {
		"jid": jid,
		"message": message
	}
	res = call_baileys_api("send-message", method="POST", data=payload)

	if send_accepted(res):
		record_outgoing(res, jid, message, hub, "Manual Test Message")
		frappe.db.commit()
	elif res.get("status") == "ok":
		return {"status": "error", "error": "Baileys did not return a message ID"}

	return res


@frappe.whitelist()
def simulate_whatsapp_message(text: str, sender_phone: str = "966569589664") -> dict:
	require_hub_permission("write")
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
