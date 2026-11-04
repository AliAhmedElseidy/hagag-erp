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
		code = res.get("code") or res.get("pairing_code")
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
			"pairing_code": code,
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

def call_ai_api(
	user_message: str,
	provider: str = "Gemini",
	api_key: str = None,
	model: str = "Gemini 3.5 Flash Lite",
	system_prompt: str = None,
	context_history: list = None
) -> dict:
	"""
	Calls AI API (Gemini or OpenAI-compatible) with strict error isolation and timeout.
	Returns dict: {"status": "ok"|"error", "reply": str, "error": str}
	Never masks API failures with repeated welcome templates.
	"""
	if not api_key:
		return {"status": "error", "error": "لم يتم تكوين مفتاح الذكاء الاصطناعي"}

	clean_model = (model or "").strip()
	if provider == "Gemini":
		model_map = {
			"gemini 3.5 flash lite": "gemini-3.5-flash-lite",
			"gemini-3.5-flash-lite": "gemini-3.5-flash-lite",
			"gemini 3.8 flash": "gemini-3.5-flash-lite",
			"gemini 2.5 flash": "gemini-3.5-flash-lite",
			"gemini-2.5-flash": "gemini-3.5-flash-lite",
			"gemini 1.5 flash": "gemini-3.5-flash-lite",
			"gemini-1.5-flash": "gemini-3.5-flash-lite",
			"gemini-flash": "gemini-3.5-flash-lite",
			"gemini flash": "gemini-3.5-flash-lite"
		}
		clean_model = model_map.get(clean_model.lower(), "gemini-3.5-flash-lite")

	try:
		if provider == "Gemini":
			url = f"https://generativelanguage.googleapis.com/v1beta/models/{clean_model}:generateContent?key={api_key}"

			contents = []
			if context_history and isinstance(context_history, list):
				for turn in context_history:
					if turn.get("user"):
						contents.append({"role": "user", "parts": [{"text": turn["user"]}]})
					if turn.get("model"):
						contents.append({"role": "model", "parts": [{"text": turn["model"]}]})
			contents.append({"role": "user", "parts": [{"text": user_message}]})

			payload = {
				"contents": contents,
				"systemInstruction": {
					"parts": [{"text": system_prompt or "أنت المساعد المالي والإداري لمنظومة الصعيدي (شركة ركن سبل الأفق للمقاولات). أجب بأسلوب مهني، مباشر، وموجز باللغة العربية دون استبدال الأسئلة المحاسبية بقوائم ثابتة."}]
				},
				"generationConfig": {
					"maxOutputTokens": 600,
					"temperature": 0.6
				}
			}
			resp = requests.post(url, json=payload, timeout=20)
			data = resp.json()

			if resp.status_code != 200:
				err = data.get("error", {}).get("message", str(resp.status_code))
				frappe.log_error(f"Gemini API Error [{resp.status_code}]: {err}", "Elsaidy WhatsApp Hub AI")
				return {"status": "error", "error": f"خطأ في الاتصال بالنموذج ({resp.status_code}): {err}"}

			candidates = data.get("candidates", [])
			if not candidates:
				return {"status": "error", "error": "لم يقدم النموذج رداً"}

			reply_text = (
				candidates[0]
				.get("content", {})
				.get("parts", [{}])[0]
				.get("text", "")
				.strip()
			)
			return {"status": "ok", "reply": reply_text}

		elif provider in ("OpenAI", "Custom API"):
			url = "https://api.openai.com/v1/chat/completions"
			headers = {
				"Authorization": f"Bearer {api_key}",
				"Content-Type": "application/json"
			}
			messages = [{"role": "system", "content": system_prompt or "أنت المساعد الذكي لشركة الصعيدي للمقاولات."}]
			if context_history and isinstance(context_history, list):
				for turn in context_history:
					if turn.get("user"):
						messages.append({"role": "user", "content": turn["user"]})
					if turn.get("model"):
						messages.append({"role": "assistant", "content": turn["model"]})
			messages.append({"role": "user", "content": user_message})

			payload = {
				"model": clean_model or "gpt-4o-mini",
				"messages": messages,
				"max_tokens": 600,
				"temperature": 0.7
			}
			resp = requests.post(url, json=payload, headers=headers, timeout=20)
			data = resp.json()

			if resp.status_code != 200:
				err = data.get("error", {}).get("message", str(resp.status_code))
				frappe.log_error(f"OpenAI API Error: {err}", "Elsaidy WhatsApp Hub AI")
				return {"status": "error", "error": f"خطأ في الاتصال ({resp.status_code}): {err}"}

			reply_text = data["choices"][0]["message"]["content"].strip()
			return {"status": "ok", "reply": reply_text}

		else:
			return {"status": "error", "error": f"المزود {provider} غير مدعوم"}

	except requests.Timeout:
		frappe.log_error("AI API Timeout (>20s)", "Elsaidy WhatsApp Hub AI")
		return {"status": "error", "error": "تجاوز مهلة الاستجابة من خادم الذكاء الاصطناعي"}
	except Exception as e:
		frappe.log_error(f"AI API Exception: {str(e)}", "Elsaidy WhatsApp Hub AI")
		return {"status": "error", "error": str(e)}


def generate_local_fallback_reply(user_message: str, error_context: str = "") -> str:
	"""
	Local Rule-Based Fallback Engine.
	Provides clear instructions only when explicitly requested or on system errors.
	"""
	if error_context:
		return (
			f"⚠️ *تنبيه:* {error_context}\n"
			f"━━━━━━━━━━━━━━━━━━━\n"
			f"يمكنك استخدام الأوامر المباشرة المعتمدة:\n"
			f"• *رصيد العهدة* — للاستعلام عن رصيدك المالي المعتمد.\n"
			f"• *صرفت [المبلغ] ريال [البيان]* — لتسجيل مصروف عهدة جديد."
		)

	return (
		"مرحباً بك في *منظومة الصعيدي الذكية* 🏗️\n"
		"━━━━━━━━━━━━━━━━━━━\n"
		"أنا المساعد المالي والإداري لخدمتكم. يمكنك استخدام:\n"
		"• *رصيد العهدة* — لعرض رصيدك المالي المعتمد في دفتر الأستاذ العام.\n"
		"• *صرفت 300 ريال ديزل* — لتسجيل مصروف عهدة والتأكيد قبل إنشاء المسودة.\n"
		"• الاستفسارات المباشرة — وسأجيبك فوراً."
	)


# ──────────────────────────────────────────────────────────────────────────────
# Strict Whitelist Security Gate & Allowlist Verification
# ──────────────────────────────────────────────────────────────────────────────

def get_verified_contact_rule(sender_phone: str = "", sender_lid: str = "", sender_jid: str = "") -> dict | None:
	"""
	Strict Whitelist Security Gate:
	Primary source of truth: Elsaidy WhatsApp Contact Rule table in MariaDB.
	Returns the matching active rule dict ONLY if:
	  1. A rule exists matching the normalized phone or exact LID.
	  2. The rule has is_active == 1.
	Returns None if:
	  - No matching rule is found in the allowlist.
	  - Rule has is_active == 0 (deactivated by admin).
	  - Sender identity is ambiguous or unresolvable.
	Never treats phone contacts, raw employee records, or incoming messages as authorization.
	"""
	norm_phone = normalize_phone_number(sender_phone) if sender_phone else ""
	if not norm_phone and sender_jid and sender_jid.endswith("@s.whatsapp.net"):
		norm_phone = normalize_phone_number(sender_jid.split("@")[0])

	clean_lid = (sender_lid or "").strip()
	if not clean_lid and sender_jid and sender_jid.endswith("@lid"):
		clean_lid = sender_jid.strip()

	if not norm_phone and not clean_lid:
		frappe.logger("whatsapp_security").warning(
			f"[SecurityGate] Refusing unresolvable sender: phone='{sender_phone}', lid='{sender_lid}', jid='{sender_jid}'"
		)
		return None

	try:
		active_rules = frappe.db.sql("""
			SELECT name, contact_name, phone_number, whatsapp_lid, is_active, role, linked_employee,
			       can_record_expenses, can_request_balance, can_create_purchase_invoice,
			       default_project, default_cost_center, default_custody_account
			FROM `tabElsaidy WhatsApp Contact Rule`
			WHERE is_active = 1
		""", as_dict=True)
	except Exception as db_err:
		frappe.logger("whatsapp_security").error(f"[SecurityGate] DB error querying contact rules: {db_err}")
		return None  # Fail secure

	if not active_rules:
		return None

	matched_rule = None

	# 1. First priority: Exact LID Match
	if clean_lid:
		lid_prefix = clean_lid.split("@")[0]
		for rule in active_rules:
			r_lid = (rule.get("whatsapp_lid") or "").strip()
			if r_lid and r_lid.split("@")[0] == lid_prefix:
				matched_rule = rule
				break

	# 2. Second priority: Normalized Phone Number Match
	if not matched_rule and norm_phone:
		for rule in active_rules:
			r_phone = normalize_phone_number(rule.get("phone_number") or "")
			if not r_phone:
				continue
			if norm_phone == r_phone:
				matched_rule = rule
				break
			if len(norm_phone) >= 9 and len(r_phone) >= 9:
				if norm_phone.endswith(r_phone) or r_phone.endswith(norm_phone):
					matched_rule = rule
					break

	return matched_rule


# ──────────────────────────────────────────────────────────────────────────────
# Accounting & Custody Service Integration
# ──────────────────────────────────────────────────────────────────────────────

def query_employee_custody_balance(sender_phone: str, sender_lid: str = None) -> dict:
	"""
	Queries real posted custody balance directly from approved GL Entries in MariaDB.
	Strictly enforces identity, allowlist presence, and permission verification.
	"""
	contact_rule = get_verified_contact_rule(sender_phone=sender_phone, sender_lid=sender_lid)
	if not contact_rule:
		return {
			"authorized": False,
			"reply": None,
			"reply_source": "Security",
			"intent": "Unauthorized"
		}

	if not contact_rule.get("can_request_balance"):
		return {
			"authorized": False,
			"reply_source": "Security",
			"intent": "Balance Permission Denied",
			"reply": "⛔ ليس لديك صلاحية الاستعلام عن رصيد العهدة عبر واتساب من هذا الرقم."
		}

	emp_id = contact_rule.get("linked_employee") or contact_rule.get("employee")
	employee_doc = None
	if emp_id:
		employee_doc = frappe.db.get_value(
			"Employee",
			{"name": emp_id, "status": "Active"},
			["name", "employee_name", "status", "company"],
			as_dict=True
		)

	if not employee_doc:
		return {
			"authorized": False,
			"reply_source": "Accounting Tool",
			"intent": "Unlinked Employee",
			"reply": "⚠️ لم يتم ربط هذا الرقم بملف موظف نشط في النظام المحاسبي. يرجى مراجعة إدارة الموارد البشرية."
		}

	# 2. Custody Account & GL Entries
	company = (employee_doc.get("company") if employee_doc else None) or (contact_rule.get("company") if contact_rule else None) or "ركن سبل الافق"
	custody_account = (contact_rule.get("default_custody_account") if contact_rule else None)
	if not custody_account:
		custody_account = "1120 - عهد نقدية للمهندسين والمشرفين - Rkn"

	emp_name = employee_doc.get("employee_name") or (contact_rule.get("contact_name") if contact_rule else "الموظف")
	emp_id = employee_doc.get("name")

	# Query approved GL Entries (docstatus=1 strictly)
	if emp_id:
		gl_stats = frappe.db.sql("""
			SELECT 
				COALESCE(SUM(debit), 0) as total_debit,
				COALESCE(SUM(credit), 0) as total_credit,
				COALESCE(SUM(debit - credit), 0) as net_balance
			FROM `tabGL Entry`
			WHERE account = %s AND is_cancelled = 0 AND docstatus = 1
			  AND ((party_type = 'Employee' AND party = %s) OR party IS NULL)
		""", (custody_account, emp_id), as_dict=True)
	else:
		gl_stats = frappe.db.sql("""
			SELECT 
				COALESCE(SUM(debit), 0) as total_debit,
				COALESCE(SUM(credit), 0) as total_credit,
				COALESCE(SUM(debit - credit), 0) as net_balance
			FROM `tabGL Entry`
			WHERE account = %s AND is_cancelled = 0 AND docstatus = 1
		""", (custody_account,), as_dict=True)
	
	stats = gl_stats[0] if gl_stats else {"total_debit": 0, "total_credit": 0, "net_balance": 0}
	total_debit = flt(stats["total_debit"])
	total_credit = flt(stats["total_credit"])
	net_balance = flt(stats["net_balance"])

	# Query pending draft entries (docstatus=0)
	draft_stats = frappe.db.sql("""
		SELECT COUNT(*) as draft_count, COALESCE(SUM(total_debit), 0) as draft_total
		FROM `tabJournal Entry`
		WHERE docstatus = 0 AND company = %s
	""", (company,), as_dict=True)
	draft_count = cint(draft_stats[0]["draft_count"]) if draft_stats else 0
	draft_total = flt(draft_stats[0]["draft_total"]) if draft_stats else 0.0

	emp_name = employee_doc.get("employee_name") or (contact_rule.get("contact_name") if contact_rule else "الموظف")
	emp_id = employee_doc.get("name") or "HR-EMP-00001"
	acc_display = custody_account.split(" - ")[1] if " - " in custody_account else custody_account

	reply_lines = [
		"💰 *كشف رصيد العهدة المعتمد*",
		"━━━━━━━━━━━━━━━━━━━",
		f"👤 *الموظف:* {emp_name} (`{emp_id}`)",
		f"🏢 *الشركة:* {company}",
		f"🏦 *حساب العهدة:* {acc_display}",
		"───────────────────",
		f"📥 *إجمالي العهد المستلمة (مدين):* {total_debit:,.2f} ر.س",
		f"📤 *إجمالي المصروفات المعتمدة (دائن):* {total_credit:,.2f} ر.س",
		f"⚖️ *صافي الرصيد المتاح الفعلي:* `{net_balance:,.2f}` ر.س"
	]
	if draft_count > 0:
		reply_lines.append(f"⏳ *حركات تحت المراجعة (مسودات):* {draft_count} قيد بقيمة {draft_total:,.2f} ر.س")
	reply_lines.extend([
		"━━━━━━━━━━━━━━━━━━━",
		"ℹ️ *تم استخراج الرصيد مباشرة من دفتر الأستاذ العام المعتمد (GL Entry) بتوقيت الرياض.*"
	])

	return {
		"authorized": True,
		"reply_source": "Accounting Tool",
		"intent": "Custody Balance Query",
		"reply": "\n".join(reply_lines),
		"balance": net_balance,
		"employee_id": emp_id
	}


# ──────────────────────────────────────────────────────────────────────────────
# Natural Language Parsing & Interactive Expenses
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


def process_expense_interactive(text: str, sender_phone: str, sender_name: str, contact_rule: dict = None, hub: dict = None) -> dict:
	"""
	Parses expense details and asks user for confirmation before creating draft.
	Never auto-posts financial entries.
	"""
	parsed = parse_expense_from_text(text)
	if not parsed or not parsed.get("amount") or parsed["amount"] <= 0:
		return None

	if not contact_rule:
		contact_rule = get_verified_contact_rule(sender_phone=sender_phone)
	if not contact_rule:
		return None

	if not contact_rule.get("can_record_expenses"):
		return {
			"reply_source": "Security",
			"intent": "Expense Permission Denied",
			"reply": "⛔ ليس لديك صلاحية تسجيل المصاريف عبر واتساب من هذا الرقم."
		}

	amount = flt(parsed["amount"])
	is_inclusive = parsed.get("is_inclusive", True)
	
	# Detect expense category
	norm = text.lower()
	category = "مصروفات عامة"
	if any(k in norm for k in ["ديزل", "بنزين", "وقود", "محروقات"]):
		category = "وقود ومحروقات (ديزل/بنزين)"
	elif any(k in norm for k in ["صيانة", "تصليح", "قطع غيار"]):
		category = "صيانة وإصلاحات"
	elif any(k in norm for k in ["سكن", "فندق", "إقامة"]):
		category = "إقامة ومصاريف موقع"
	elif any(k in norm for k in ["أدوات", "مواد", "مشتريات"]):
		category = "مشتريات ومواد موقع"

	# Detect project
	target_project = contact_rule.get("default_project") if contact_rule else None
	project_name = "عام (غير محدد)"
	if target_project:
		project_name = frappe.db.get_value("Project", target_project, "project_name") or target_project
	else:
		# Search if user mentioned project in text
		projs = frappe.db.sql("SELECT name, project_name FROM `tabProject` WHERE status = 'Open'", as_dict=True)
		for p in projs:
			if p.project_name and p.project_name.lower() in norm:
				target_project = p.name
				project_name = p.project_name
				break

	# Save pending state in cache (15 min TTL)
	cache_key = f"wa_conv_state_{sender_phone}"
	frappe.cache().set_value(cache_key, {
		"pending_action": "confirm_draft_expense",
		"amount": amount,
		"category": category,
		"project": target_project,
		"project_name": project_name,
		"is_inclusive": is_inclusive,
		"raw_text": text,
		"timestamp": time.time()
	}, expires_in_sec=900)

	vat_str = "شامل الضريبة 15%" if is_inclusive else "قبل الضريبة (يضاف 15%)"
	return {
		"reply_source": "Accounting Tool",
		"intent": "Expense Confirmation Request",
		"reply": (
			f"📝 *طلب تسجيل مصروف عهدة (مسودة)*\n"
			f"━━━━━━━━━━━━━━━━━━━\n"
			f"💵 *المبلغ:* {amount:,.2f} ر.س ({vat_str})\n"
			f"🏷️ *التصنيف:* {category}\n"
			f"🏗️ *المشروع:* {project_name}\n"
			f"👤 *المسؤول:* {sender_name or sender_phone}\n"
			f"━━━━━━━━━━━━━━━━━━━\n"
			f"👉 هل تود إنشاء مسودة القيد الآن؟\n"
			f"أرسل *أيوة* أو *تأكيد* للمتابعة، أو *لا* للإلغاء."
		)
	}


def handle_conversation_context(text: str, sender_phone: str, sender_name: str, contact_rule: dict = None, hub: dict = None) -> dict:
	"""
	Evaluates user input against pending actions in conversation state (affirmations/negations/context).
	"""
	cache_key = f"wa_conv_state_{sender_phone}"
	conv_state = frappe.cache().get_value(cache_key)
	if not conv_state:
		return None

	norm = text.strip().lower()
	is_affirmation = norm in [
		"أيوة", "ايوة", "اه", "آه", "نعم", "تمام", "أكد", "تأكيد", "موافق", "yes", "ok",
		"اكيد", "أكيد", "صحيح", "ايوه تمام", "أيوة تمام", "اعتمد", "سجل"
	]
	is_negation = norm in [
		"لا", "لأ", "إلغاء", "الغاء", "تراجع", "مش دلوقتي", "cancel", "no", "لا شكرا", "لا شكراً"
	]

	pending_action = conv_state.get("pending_action")

	# 1. Handle Pending Expense Confirmation
	if pending_action == "confirm_draft_expense":
		if is_affirmation:
			from hagag_erp.tax_engine import calculate_zatca_tax, create_draft_journal_entry, get_company_tax_accounts

			company = (hub.default_company if hub and hub.default_company else None) or "ركن سبل الافق"
			amount = conv_state.get("amount", 0.0)
			is_inclusive = conv_state.get("is_inclusive", True)
			project = conv_state.get("project")
			project_name = conv_state.get("project_name", "عام")
			category = conv_state.get("category", "مصروفات عامة")
			raw_text = conv_state.get("raw_text", text)

			tax_calc = calculate_zatca_tax(Decimal(str(amount)), is_inclusive=is_inclusive)
			tax_accs = get_company_tax_accounts(company)

			expense_account = (hub.default_expense_account if hub and hub.default_expense_account else None) or tax_accs.get("default_expense_account")
			vat_account = (hub.default_vat_account if hub and hub.default_vat_account else None) or tax_accs.get("input_vat_account")
			credit_account = (contact_rule.get("default_custody_account") if contact_rule else None) or "1120 - عهد نقدية للمهندسين والمشرفين - Rkn"

			if not expense_account:
				expense_account = "5120 - مصروف الوقود والمحروقات - Rkn"
			if not vat_account:
				vat_account = frappe.db.get_value("Account", {"company": company, "account_type": "Tax", "is_group": 0}, "name")

			cost_center = (contact_rule.get("default_cost_center") if contact_rule else None) or (hub.default_cost_center if hub else None) or "رئيسي - Rkn"

			je_lines = [
				{
					"account": expense_account,
					"debit": float(tax_calc["net_amount"]),
					"credit": 0.0,
					"project": project,
					"cost_center": cost_center,
					"user_remark": f"مصروف عبر واتساب ({category}): {raw_text[:140]}"
				},
				{
					"account": vat_account,
					"debit": float(tax_calc["tax_amount"]),
					"credit": 0.0,
					"project": project,
					"cost_center": cost_center,
					"user_remark": f"ضريبة القيمة المضافة 15% ZATCA: {raw_text[:140]}"
				},
				{
					"account": credit_account,
					"debit": 0.0,
					"credit": float(tax_calc["total_amount"]),
					"project": project,
					"cost_center": cost_center,
					"party_type": "Employee" if (contact_rule and contact_rule.get("employee")) else None,
					"party": contact_rule.get("employee") if contact_rule else None,
					"user_remark": f"دفعة من عهدة: {sender_name or sender_phone}"
				}
			]

			jv = create_draft_journal_entry(
				company=company,
				accounts_data=je_lines,
				user_remark=f"مصروف معتمد كمسودة عبر واتساب من {sender_name} ({sender_phone}).\nالبيان: {raw_text}",
				reference_id=f"WA-CONF-{int(time.time())}"
			)

			# Clear cache state
			frappe.cache().delete_value(cache_key)

			doc_url = f"https://erp.elsaidy.org/app/journal-entry/{jv.name}"
			return {
				"reply_source": "Accounting Tool",
				"intent": "Expense Draft Confirmed",
				"linked_doc_type": "Journal Entry",
				"linked_doc_name": jv.name,
				"reply": (
					f"✅ *تم إنشاء مسودة القيد بنجاح (بانتظار الاعتماد) 🧾*\n"
					f"━━━━━━━━━━━━━━━━━━━\n"
					f"🔖 *رقم القيد:* `{jv.name}`\n"
					f"🏗️ *المشروع:* {project_name}\n"
					f"💵 *المبلغ الصافي:* {tax_calc['net_amount']:,.2f} ر.س\n"
					f"🏛️ *ضريبة القيمة المضافة (15%):* {tax_calc['tax_amount']:,.2f} ر.س\n"
					f"💰 *المجموع الإجمالي:* {tax_calc['total_amount']:,.2f} ر.س\n"
					f"👤 *المسجّل:* {sender_name or sender_phone}\n"
					f"━━━━━━━━━━━━━━━━━━━\n"
					f"🔗 *رابط مراجعة واعتماد القيد:*\n{doc_url}\n"
					f"⚠️ *ملاحظة:* القيد تم حفظه كمسودة (Draft) ولا يؤثر على القوائم المالية حتى يتم اعتماده."
				)
			}

		elif is_negation:
			frappe.cache().delete_value(cache_key)
			return {
				"reply_source": "Accounting Tool",
				"intent": "Expense Draft Cancelled",
				"reply": "❌ تم إلغاء تسجيل المصروف بناءً على طلبك. كيف يمكنني مساعدتك؟"
			}

	return None


def resolve_destination_jid(target: str) -> str:
	"""
	Resolves recipient identifier to canonical delivery JID.
	For 1-to-1 contacts, ALWAYS delivers to {norm_phone}@s.whatsapp.net.
	NEVER delivers to @lid because direct LID delivery triggers 'Waiting for this message'.
	"""
	clean = (target or "").strip()
	if not clean:
		return ""

	if clean.endswith("@g.us"):
		return clean

	# If someone passed an explicit LID, resolve back to phone number
	if clean.endswith("@lid"):
		clean_digits = clean.split("@")[0].split(":")[0]
		try:
			rule = frappe.db.sql("""
				SELECT phone_number FROM `tabElsaidy WhatsApp Contact Rule`
				WHERE whatsapp_lid LIKE %s AND is_active = 1 LIMIT 1
			""", (f"%{clean_digits}%",), as_dict=True)
			if rule and rule[0].get("phone_number"):
				norm_p = normalize_phone_number(rule[0]["phone_number"])
				if norm_p:
					return f"{norm_p}@s.whatsapp.net"
		except Exception:
			pass
		try:
			log_p = frappe.db.sql("""
				SELECT sender_phone FROM `tabElsaidy WhatsApp Log`
				WHERE sender_lid LIKE %s AND sender_phone IS NOT NULL AND sender_phone != ''
				ORDER BY creation DESC LIMIT 1
			""", (f"%{clean_digits}%",), as_dict=True)
			if log_p and log_p[0].get("sender_phone"):
				norm_p = normalize_phone_number(log_p[0]["sender_phone"])
				if norm_p:
					return f"{norm_p}@s.whatsapp.net"
		except Exception:
			pass
		frappe.logger("whatsapp").warn(f"[ResolveJID] Unresolvable LID destination: {clean}")
		return clean

	norm_phone = normalize_phone_number(clean)
	if not norm_phone:
		return clean if "@" in clean else f"{clean}@s.whatsapp.net"

	# For any phone number, ALWAYS deliver to {norm_phone}@s.whatsapp.net!
	return f"{norm_phone}@s.whatsapp.net"


@frappe.whitelist()
def sync_all_contact_mappings_to_baileys() -> dict:
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
	if bot_phone and (bot_phone in clean_jid or clean_jid.startswith(bot_phone)):
		frappe.logger("whatsapp").warn(f"[SendBlocked] Refusing to reply to bot's own number: {clean_jid}")
		return {"status": "ignored", "reason": "Cannot reply to bot itself"}

	# Strict Whitelist Guard: Destination must be an active allowlisted contact or allowed group
	if not clean_jid.endswith("@g.us"):
		recipient_phone = clean_jid.split("@")[0] if "@s.whatsapp.net" in clean_jid else ""
		recipient_lid = clean_jid if "@lid" in clean_jid else ""
		rule = get_verified_contact_rule(sender_phone=recipient_phone, sender_lid=recipient_lid, sender_jid=clean_jid)
		if not rule:
			frappe.logger("whatsapp_security").error(
				f"[SendBlocked] Strict allowlist blocked outgoing reply to unauthorized recipient: {clean_jid}"
			)
			return {"status": "ignored", "reason": "Recipient not in active allowlist"}
	else:
		is_allowed_group = False
		if frappe.db.table_exists("Elsaidy WhatsApp Group Rule"):
			is_allowed_group = bool(frappe.db.sql("""
				SELECT 1 FROM `tabElsaidy WhatsApp Group Rule`
				WHERE is_active = 1 AND group_jid = %s
				LIMIT 1
			""", (clean_jid,)))
		if not is_allowed_group:
			frappe.logger("whatsapp_security").error(
				f"[SendBlocked] Strict allowlist blocked outgoing reply to unauthorized group: {clean_jid}"
			)
			return {"status": "ignored", "reason": "Group not in active allowlist"}

	# Always resolve to canonical delivery JID ({phone}@s.whatsapp.net)
	target_jid = resolve_destination_jid(clean_jid)

	payload = {
		"jid": target_jid,
		"message": text,
		"quoted_message_id": quoted_msg_id
	}
	return call_baileys_api("send-message", method="POST", data=payload)


# ──────────────────────────────────────────────────────────────────────────────
# Core Webhook Event Receiver
# ──────────────────────────────────────────────────────────────────────────────

@frappe.whitelist(allow_guest=True)
def receive_baileys_event():
	"""
	Core Webhook Endpoint invoked by Baileys Node.js container:
	1. Real-time delivery status updates ('status_update' / 'messages.update').
	2. Inbound messages ('message' / 'messages.upsert').
	3. Dynamic Identity Resolution & Auto-Learning (LID <-> Phone).
	4. Conversation State & Context Tracking ("أيوة" / "آه").
	5. Accounting Tool: Real posted custody balance from approved GL Entries.
	6. Interactive Expense Recording (Confirmation before Draft creation).
	7. Gemini AI for Natural Greetings & General Inquiries.
	8. Transparent Reply Source Logging: [Accounting Tool], [Gemini AI], [Fallback Template].
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

	# ── 1.1 Handle Delivery Status Updates ────────────────────────────────────
	if event_type in ("status_update", "messages.update"):
		msg_id = payload.get("message_id") or payload.get("msg_id")
		raw_status = payload.get("status") if payload.get("status") is not None else payload.get("status_code")
		status_map = {
			0: "Failed",
			1: "Pending",
			2: "Sent",
			3: "Delivered",
			4: "Read",
			5: "Read"
		}
		delivery_status = payload.get("delivery_status") or status_map.get(raw_status, "Sent")
		if msg_id:
			try:
				frappe.db.sql("""
					UPDATE `tabElsaidy WhatsApp Log`
					SET delivery_status = %s
					WHERE message_id = %s
				""", (delivery_status, msg_id))
				frappe.db.commit()
			except Exception as upd_err:
				frappe.logger("whatsapp").warn(f"Failed to update delivery status: {upd_err}")
		return {"status": "ok", "event_type": "status_update", "message_id": msg_id, "delivery_status": delivery_status}

	if event_type not in ("message", "messages.upsert"):
		return {"status": "ignored", "reason": f"Unhandled event type: {event_type}"}

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
	remote_jid = data.get("remote_jid") or ""
	reply_jid = group_jid if is_group else (f"{sender_phone}@s.whatsapp.net" if sender_phone else (remote_jid or sender_jid))

	# 2. Strict Idempotency & Concurrency Lock Check
	lock_key = f"wa_proc_{msg_id}"
	try:
		if not frappe.cache().set_value(lock_key, 1, expires_in_sec=60):
			return {"status": "already_logged", "message_id": msg_id, "reason": "Concurrent processing"}
	except Exception:
		pass

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
	log_doc.sender_lid = sender_lid
	log_doc.is_group = 1 if is_group else 0
	log_doc.group_jid = group_jid
	log_doc.reply_jid = reply_jid
	log_doc.message_text = text
	log_doc.status = "Received"
	log_doc.delivery_status = "Delivered"

	# ── 3. Strict Allowlist Security Gate ────────────────────────────────────
	target_project = None
	target_cost_center = hub.default_cost_center if hub else "رئيسي - Rkn"
	company = (hub.default_company if hub and hub.default_company else None) or "ركن سبل الافق"
	contact_rule = None
	group_rule = None

	if is_group:
		matching_groups = []
		if frappe.db.table_exists("Elsaidy WhatsApp Group Rule"):
			matching_groups = frappe.db.sql("""
				SELECT * FROM `tabElsaidy WhatsApp Group Rule`
				WHERE is_active = 1 AND group_jid = %s
				LIMIT 1
			""", (group_jid,), as_dict=True)

		if not matching_groups:
			log_doc.status = "Ignored"
			log_doc.reply_text = None
			log_doc.extracted_intent = "[Security] Unauthorized Group Blocked"
			log_doc.error_message = f"Unauthorized group: {group_jid}"
			log_doc.insert(ignore_permissions=True)
			frappe.db.commit()
			return {"status": "rejected", "reason": "unauthorized_group", "silent_drop": True}

		group_rule = matching_groups[0]
		log_doc.group_name = group_rule.get("group_name")
		target_project = group_rule.get("default_project")
		target_cost_center = group_rule.get("default_cost_center") or target_cost_center

		if group_rule.get("require_mention"):
			bot_phone = hub.connected_phone or hub.bot_phone_number or ""
			if bot_phone and bot_phone not in text and "@" not in text:
				log_doc.status = "Ignored"
				log_doc.reply_text = None
				log_doc.error_message = "Group message ignored (require_mention active and bot not tagged)"
				log_doc.insert(ignore_permissions=True)
				frappe.db.commit()
				return {"status": "ignored", "reason": "No mention"}

		# Check participant authorization in group
		participant_jid = data.get("participant") or sender_jid
		contact_rule = get_verified_contact_rule(sender_jid=participant_jid)
	else:
		# Direct 1-to-1 Message: STRICT ALLOWLIST CHECK
		contact_rule = get_verified_contact_rule(
			sender_phone=sender_phone,
			sender_lid=sender_lid,
			sender_jid=sender_jid
		)

		if not contact_rule:
			# STRICT SILENT DROP: No automated reply, no rejection message, no greeting!
			log_doc.status = "Ignored"
			log_doc.reply_text = None
			log_doc.extracted_intent = "[Security] Unauthorized Sender Blocked"
			log_doc.error_message = f"Unauthorized direct sender: {sender_phone or sender_jid or sender_lid} (Not in active allowlist)"
			log_doc.insert(ignore_permissions=True)
			frappe.db.commit()
			frappe.logger("whatsapp_security").warning(
				f"[StrictAllowlist] Blocked unauthorized message from '{sender_phone or sender_jid or sender_lid}'. Silent drop (Zero reply)."
			)
			return {
				"status": "rejected",
				"reason": "unauthorized_allowlist",
				"silent_drop": True,
				"message": "Sender not in active allowlist. Silent drop (Zero reply)."
			}

		target_project = contact_rule.get("default_project")
		target_cost_center = contact_rule.get("default_cost_center") or target_cost_center

		# Dynamic Auto-Learning of sender_lid for verified contact
		c_lid = getattr(contact_rule, "whatsapp_lid", "") if hasattr(contact_rule, "whatsapp_lid") else (contact_rule.get("whatsapp_lid") or "")
		if sender_lid and not c_lid:
			try:
				frappe.db.set_value("Elsaidy WhatsApp Contact Rule", contact_rule.get("name"), "whatsapp_lid", sender_lid, update_modified=False)
				frappe.db.commit()
				call_baileys_api("sync-contact-mapping", method="POST", data={
					"mappings": [{"lid": sender_lid, "phone": normalize_phone_number(contact_rule.get("phone_number"))}]
				})
			except Exception:
				pass

	# ── 4. Check Human Takeover Active ───────────────────────────────────────
	is_takeover = False
	if sender_phone:
		try:
			is_takeover = bool(frappe.cache().get_value(f"wa_takeover_{sender_phone}"))
		except Exception:
			is_takeover = False

	if is_takeover:
		log_doc.extracted_intent = "[Human Takeover] Auto-reply Suppressed"
		log_doc.status = "Received"
		log_doc.reply_text = None
		log_doc.insert(ignore_permissions=True)
		frappe.db.commit()
		return {
			"status": "ok",
			"message_id": msg_id,
			"human_takeover": True,
			"log": log_doc.name,
			"message": "Message logged. Automated reply suppressed (Human takeover mode active)."
		}

	# ── 5. Bot Mode Check ────────────────────────────────────────────────────
	bot_mode = (hub.bot_mode if hub and hub.bot_mode else "AI + Accounting Hybrid")
	if bot_mode == "Disabled / Log Only":
		log_doc.extracted_intent = "[Disabled Mode] Log Only"
		log_doc.status = "Ignored"
		log_doc.insert(ignore_permissions=True)
		frappe.db.commit()
		return {"status": "ok", "message_id": msg_id, "log": log_doc.name, "mode": "disabled"}

	reply_content = None
	created_doc = None
	reply_source = "Unknown"
	intent_name = "General"

	norm_text = text.strip().lower()

	# ── 6. Conversation State & Context Engine (Affirmations / Negations) ────
	context_res = handle_conversation_context(
		text=text,
		sender_phone=sender_phone,
		sender_name=sender_name,
		contact_rule=contact_rule,
		hub=hub
	)
	if context_res:
		reply_content = context_res.get("reply")
		reply_source = context_res.get("reply_source", "Accounting Tool")
		intent_name = context_res.get("intent", "Context Handled")
		if context_res.get("linked_doc_name"):
			log_doc.linked_document_type = context_res.get("linked_doc_type", "Journal Entry")
			log_doc.linked_document_name = context_res.get("linked_doc_name")
			log_doc.status = "Processed"

	# ── 7. Custody Balance Query (Accounting Tool) ───────────────────────────
	if not reply_content:
		balance_keywords = [
			"رصيد", "الرصيد", "رصيد العهدة", "رصيد العهده", "رصيدي", "كم باقي",
			"فاضل كام", "متبقي كام", "كشف حساب", "تسوية العهدة", "تسوية عهدة",
			"كشف العهدة", "رصيد عهدة", "رصيد سلف", "كم في العهدة", "كم في العهده"
		]
		is_balance_query = any(kw in norm_text for kw in balance_keywords)
		
		# Ensure not an expense command (e.g. "صرفت من العهدة 300")
		is_expense_syntax = any(kw in norm_text for kw in ["صرف", "دفع", "اشتريت", "شراء", "فاتورة"]) and re.search(r"\d+", norm_text)

		if is_balance_query and not is_expense_syntax:
			bal_res = query_employee_custody_balance(sender_phone=sender_phone, sender_lid=sender_lid)
			reply_content = bal_res.get("reply")
			reply_source = bal_res.get("reply_source", "Accounting Tool")
			intent_name = bal_res.get("intent", "Custody Balance Query")

	# ── 8. Expense Registration & Interactive Confirmation ───────────────────
	if not reply_content and bot_mode != "AI Assistant Only":
		expense_res = process_expense_interactive(
			text=text,
			sender_phone=sender_phone,
			sender_name=sender_name,
			contact_rule=contact_rule,
			hub=hub
		)
		if expense_res:
			reply_content = expense_res.get("reply")
			reply_source = expense_res.get("reply_source", "Accounting Tool")
			intent_name = expense_res.get("intent", "Expense Confirmation Request")

	# ── 9. Explicit Help / Start Over Request ────────────────────────────────
	if not reply_content:
		help_keywords = ["مساعدة", "مساعده", "تعليمات", "ابدأ من جديد", "ابدا من جديد", "البداية", "البدايه", "القائمة", "القائمه", "اوامر", "أوامر", "help", "start", "menu"]
		if any(kw in norm_text for kw in help_keywords):
			reply_content = generate_local_fallback_reply(text)
			reply_source = "Fallback Template"
			intent_name = "Help Menu"

	# ── 10. Gemini AI: Natural Greetings & General Questions ─────────────────
	if not reply_content:
		enable_ai = cint(hub.enable_ai_reply if hub else 0)
		ai_provider = (hub.ai_provider if hub and hub.ai_provider else "Gemini")
		ai_api_key = None
		if hub and hasattr(hub, "get_password"):
			try:
				ai_api_key = hub.get_password("ai_api_key", raise_exception=False) or None
			except Exception:
				ai_api_key = None

		ai_model = (hub.ai_model if hub and hub.ai_model else "Gemini 3.5 Flash Lite")
		ai_system_prompt = (
			hub.ai_system_prompt
			if hub and hub.ai_system_prompt
			else "أنت المساعد المالي والإداري لمنظومة الصعيدي للمقاولات (شركة ركن سبل الأفق للمقاولات، شركة الجابري، Byte Zone). أجب بأسلوب ترحيبي مهني، مباشر، وموجز باللغة العربية دون استبدال الاستفسارات المحاسبية بقوائم ثابتة."
		)

		# Fetch recent conversation context for contextual replies (e.g. "آه")
		context_history = []
		try:
			last_logs = frappe.db.sql("""
				SELECT direction, message_text, reply_text
				FROM `tabElsaidy WhatsApp Log`
				WHERE (sender_phone = %s OR receiver_phone = %s)
				ORDER BY creation DESC
				LIMIT 2
			""", (sender_phone, sender_phone), as_dict=True)
			if last_logs:
				for l in reversed(last_logs):
					if l.get("message_text"):
						context_history.append({"user": l["message_text"]})
					if l.get("reply_text"):
						context_history.append({"model": l["reply_text"]})
		except Exception:
			pass

		# Greetings detection
		greeting_words = ["مساء الفل", "مساء الخير", "صباح الخير", "السلام عليكم", "مرحبا", "مرحباً", "أهلاً", "اهلا", "سلام عليكم", "هاي", "hello", "hi"]
		is_greeting = any(gw in norm_text for gw in greeting_words)

		if enable_ai and ai_api_key and bot_mode != "Accounting Commands Only":
			ai_res = call_ai_api(
				user_message=text,
				provider=ai_provider,
				api_key=ai_api_key,
				model=ai_model,
				system_prompt=ai_system_prompt,
				context_history=context_history
			)
			if ai_res.get("status") == "ok":
				reply_content = ai_res.get("reply")
				reply_source = "Gemini AI"
				intent_name = "Natural Greeting" if is_greeting else "General Inquiry"
			else:
				# Log error clearly and return polite error without silent menu
				err_msg = ai_res.get("error", "فشل الاتصال بالذكاء الاصطناعي")
				reply_content = (
					f"⚠️ أواجه صعوبة مؤقتة في معالجة طلبك عبر الذكاء الاصطناعي.\n"
					f"يمكنك استخدام الأوامر المباشرة:\n"
					f"• *رصيد العهدة* — للاستعلام المالي المباشر.\n"
					f"• *صرفت [المبلغ] ريال [البيان]* — لتسجيل مصروف جديد."
				)
				reply_source = "Gemini AI Error"
				intent_name = "AI Connection Error"
				log_doc.error_message = err_msg
		else:
			# Fallback when AI is disabled
			contact_display_name = (contact_rule.get("contact_name") if contact_rule else "") or "يا فندم"
			if is_greeting:
				reply_content = f"أهلاً بك يا {contact_display_name}! كيف يمكنني مساعدتك في مهامك المالية أو الإدارية اليوم؟"
				reply_source = "Fallback Template"
				intent_name = "Natural Greeting"
			else:
				reply_content = generate_local_fallback_reply(text)
				reply_source = "Fallback Template"
				intent_name = "Fallback Menu"

	# ── 11. Dispatch WhatsApp Reply ──────────────────────────────────────────
	if reply_content and hub and hub.auto_reply_enabled:
		try:
			send_baileys_reply(reply_jid, reply_content, quoted_msg_id=msg_id)
			log_doc.status = "Replied"
			log_doc.delivery_status = "Sent"
		except Exception as reply_err:
			frappe.log_error(f"WhatsApp Reply Send Error: {str(reply_err)}", "Elsaidy WhatsApp Hub")
			log_doc.error_message = str(reply_err)

	# ── 12. Save & Audit Log ─────────────────────────────────────────────────
	elapsed_ms = (time.time() - start_time) * 1000.0
	log_doc.reply_text = reply_content
	log_doc.extracted_intent = f"[{reply_source}] {intent_name}"
	log_doc.execution_time_ms = round(elapsed_ms, 2)
	log_doc.insert(ignore_permissions=True)
	frappe.db.commit()

	frappe.logger("whatsapp").info(
		f"[InboundProcessed] msg_id={msg_id} phone={sender_phone} source=[{reply_source}] intent={intent_name} time={log_doc.execution_time_ms}ms"
	)

	return {
		"status": "ok",
		"message_id": msg_id,
		"log": log_doc.name,
		"reply_source": reply_source,
		"intent": intent_name,
		"execution_time_ms": log_doc.execution_time_ms
	}


# ──────────────────────────────────────────────────────────────────────────────
# GUI Whitelisted Management Endpoints, Telemetry & Message Center
# ──────────────────────────────────────────────────────────────────────────────

@frappe.whitelist()
def get_dashboard_telemetry() -> dict:
	"""
	Aggregates real-time telemetry from Baileys engine and ERPNext MariaDB logs.
	Strictly read-only during polling to prevent database locks.
	"""
	hub = get_hub_settings()
	health_data = call_baileys_api("health", method="GET", hub_doc=hub)
	status_data = call_baileys_api("status", method="GET", hub_doc=hub)

	today_date = today()

	try:
		stats = frappe.db.sql("""
			SELECT 
				COUNT(*) as total_today,
				SUM(CASE WHEN direction = 'Incoming' THEN 1 ELSE 0 END) as incoming_today,
				SUM(CASE WHEN status = 'Replied' THEN 1 ELSE 0 END) as replied_today,
				SUM(CASE WHEN extracted_intent LIKE '%%AI%%' THEN 1 ELSE 0 END) as ai_replies_today,
				SUM(CASE WHEN extracted_intent LIKE '%%Accounting%%' THEN 1 ELSE 0 END) as accounting_today,
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
		"version": health_data.get("version") or "3.2.0-enterprise",
		"today_metrics": {
			"incoming": cint(db_metrics.get("incoming_today", 0)),
			"replied": cint(db_metrics.get("replied_today", 0)),
			"ai_replies": cint(db_metrics.get("ai_replies_today", 0)),
			"accounting_processed": cint(db_metrics.get("accounting_today", 0)),
			"failed": cint(db_metrics.get("failed_today", 0))
		}
	}


@frappe.whitelist()
def get_message_center_conversations(search: str = "", limit: int = 25, page: int = 1) -> dict:
	"""
	Fetches aggregated conversation threads for the Enterprise Message Center Inbox.
	"""
	limit = min(cint(limit) or 25, 100)
	offset = (max(cint(page), 1) - 1) * limit
	
	search_clause = ""
	args = []
	if search:
		search_term = f"%{search}%"
		search_clause = "WHERE (sender_phone LIKE %s OR receiver_phone LIKE %s OR sender_name LIKE %s OR message_text LIKE %s OR group_name LIKE %s)"
		args.extend([search_term, search_term, search_term, search_term, search_term])
	
	sql = f"""
		SELECT 
			name, message_id, direction, sender_phone, receiver_phone, sender_name,
			is_group, group_jid, group_name, status, delivery_status, extracted_intent,
			message_text, reply_text, creation,
			CASE 
				WHEN is_group = 1 THEN group_jid
				WHEN direction = 'Incoming' AND sender_phone IS NOT NULL AND sender_phone != '' THEN sender_phone
				WHEN direction = 'Outgoing' AND receiver_phone IS NOT NULL AND receiver_phone != '' THEN receiver_phone
				ELSE COALESCE(NULLIF(sender_phone, ''), NULLIF(receiver_phone, ''), sender_name, 'Unknown')
			END AS conv_partner
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
		if not partner or partner == 'Unknown':
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
	"""
	Fetches the chronological message thread for a given contact phone or group JID.
	"""
	clean_id = (target_id or "").strip()
	if not clean_id:
		return {"status": "error", "message": "Target ID required"}
	
	limit = min(cint(limit) or 50, 150)
	norm = normalize_phone_number(clean_id)
	
	logs = frappe.db.sql("""
		SELECT 
			name, message_id, direction, sender_phone, receiver_phone, sender_name,
			is_group, group_jid, group_name, status, delivery_status, extracted_intent,
			linked_document_type, linked_document_name, execution_time_ms,
			message_text, reply_text, creation
		FROM `tabElsaidy WhatsApp Log`
		WHERE sender_phone = %s 
		   OR receiver_phone = %s 
		   OR group_jid = %s
		   OR (sender_phone = %s AND %s != '')
		   OR (receiver_phone = %s AND %s != '')
		ORDER BY creation ASC
		LIMIT %s
	""", (clean_id, clean_id, clean_id, norm, norm, norm, norm, limit), as_dict=True)
	
	is_takeover = False
	try:
		is_takeover = bool(frappe.cache().get_value(f"wa_takeover_{norm or clean_id}"))
	except Exception:
		is_takeover = False
	
	return {
		"status": "ok",
		"target_id": clean_id,
		"human_takeover": is_takeover,
		"messages": logs
	}


@frappe.whitelist()
def send_conversation_reply(target_id: str, message: str, quoted_msg_id: str = None) -> dict:
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
	jid = clean_target if is_group else resolve_destination_jid(clean_target)
	
	payload = {
		"jid": jid,
		"message": text,
		"quoted_message_id": quoted_msg_id
	}
	res = call_baileys_api("send-message", method="POST", data=payload)
	
	if res.get("status") == "ok":
		log_doc = frappe.new_doc("Elsaidy WhatsApp Log")
		log_doc.message_id = res.get("msg_id") or f"HUB-OUT-{frappe.generate_hash(length=8)}"
		log_doc.direction = "Outgoing"
		log_doc.sender_phone = bot_phone
		log_doc.receiver_phone = norm_target
		log_doc.receiver_jid = jid
		log_doc.reply_jid = jid
		log_doc.message_text = text
		log_doc.status = "Replied"
		log_doc.delivery_status = "Sent"
		log_doc.extracted_intent = "[Human Direct Reply]"
		log_doc.insert(ignore_permissions=True)
		frappe.db.commit()
		return {"status": "ok", "msg_id": log_doc.message_id, "log": log_doc.name}
	
	return res


@frappe.whitelist()
def toggle_human_takeover(phone_number: str, enabled: int = 1, duration_minutes: int = 120) -> dict:
	"""
	Enables or disables Human Takeover mode for a phone number.
	When enabled, automated bot responses are suspended for this conversation.
	"""
	if not frappe.has_permission("Elsaidy WhatsApp Hub", "write"):
		frappe.throw(_("ليس لديك صلاحية لتنفيذ هذا الإجراء."))
	
	clean_phone = normalize_phone_number(phone_number)
	if not clean_phone:
		frappe.throw(_("رقم الهاتف غير صالح."))
	
	cache_key = f"wa_takeover_{clean_phone}"
	enabled_bool = bool(cint(enabled))
	
	if enabled_bool:
		duration_sec = max(cint(duration_minutes), 5) * 60
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
	"""
	Tests the configured AI engine with real round-trip latency measurement.
	"""
	if not frappe.has_permission("Elsaidy WhatsApp Hub", "write"):
		frappe.throw(_("ليس لديك صلاحية لتنفيذ هذا الإجراء."))
	
	hub = get_hub_settings()
	provider = hub.ai_provider if hub else "Gemini"
	model = hub.ai_model if hub else "Gemini 3.5 Flash Lite"
	test_prompt = prompt or "السلام عليكم، ما هي الخدمات والمشاريع التي تقدمها شركة الصعيدي؟"
	
	ai_api_key = None
	if hub and hasattr(hub, "get_password"):
		try:
			ai_api_key = hub.get_password("ai_api_key", raise_exception=False) or None
		except Exception:
			ai_api_key = None
	
	system_prompt = hub.ai_system_prompt if hub else "أنت المساعد الذكي لشركة الصعيدي للمقاولات."
	
	t0 = time.time()
	res = call_ai_api(
		user_message=test_prompt,
		provider=provider,
		api_key=ai_api_key,
		model=model,
		system_prompt=system_prompt
	)
	latency_ms = round((time.time() - t0) * 1000.0, 2)
	
	return {
		"status": res.get("status", "ok"),
		"provider": provider,
		"model": model,
		"prompt": test_prompt,
		"reply": res.get("reply") or res.get("error"),
		"latency_ms": latency_ms,
		"has_api_key": bool(ai_api_key)
	}


@frappe.whitelist()
def get_system_health_report() -> dict:
	"""
	Generates comprehensive system health status covering Docker, Baileys, Database, and Webhook.
	"""
	hub = get_hub_settings()
	baileys_health = call_baileys_api("health", method="GET", hub_doc=hub)
	baileys_status = call_baileys_api("status", method="GET", hub_doc=hub)
	
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
			"ai_model": hub.ai_model if hub else "Gemini 3.5 Flash Lite"
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
	jid = clean_recipient if is_group else resolve_destination_jid(clean_recipient)

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
		log_doc.reply_jid = jid
		log_doc.message_text = message
		log_doc.status = "Replied"
		log_doc.delivery_status = "Sent"
		log_doc.extracted_intent = "[Manual Test Message]"
		log_doc.insert(ignore_permissions=True)
		frappe.db.commit()

	return res


@frappe.whitelist()
def simulate_whatsapp_message(text: str, sender_phone: str = "201028632620") -> dict:
	"""
	Interactive Simulator testing the full Elsaidy WhatsApp auto-reply pipeline.
	Returns detected intent, real reply source, and formatted preview.
	"""
	clean_text = (text or "").strip()
	if not clean_text:
		return {"status": "error", "message": "نص الرسالة مطلوب للمحاكاة"}

	hub = get_hub_settings()
	norm_phone = normalize_phone_number(sender_phone)

	# Find contact rule
	rules = frappe.db.sql("""
		SELECT * FROM `tabElsaidy WhatsApp Contact Rule`
		WHERE is_active = 1
		  AND (phone_number = %s OR phone_number LIKE %s)
		LIMIT 1
	""", (norm_phone, f"%{norm_phone[-9:]}"), as_dict=True)
	contact_rule = rules[0] if rules else None

	sender_name = (contact_rule.get("contact_name") if contact_rule else None) or "علي الصعيدي"

	# 1. Check conversation context
	context_res = handle_conversation_context(
		text=clean_text,
		sender_phone=norm_phone,
		sender_name=sender_name,
		contact_rule=contact_rule,
		hub=hub
	)
	if context_res:
		return {
			"status": "ok",
			"mode": "Simulation",
			"reply_source": context_res.get("reply_source"),
			"detected_intent": context_res.get("intent"),
			"simulated_reply": context_res.get("reply")
		}

	# 2. Check balance query
	norm_clean = clean_text.lower()
	balance_keywords = ["رصيد", "الرصيد", "كم باقي", "فاضل كام", "متبقي كام", "كشف حساب", "تسوية العهدة", "كشف العهدة"]
	is_balance_query = any(kw in norm_clean for kw in balance_keywords)
	is_expense_syntax = any(kw in norm_clean for kw in ["صرف", "دفع", "اشتريت", "شراء", "فاتورة"]) and re.search(r"\d+", norm_clean)

	if is_balance_query and not is_expense_syntax:
		bal_res = query_employee_custody_balance(sender_phone=norm_phone)
		return {
			"status": "ok",
			"mode": "Simulation",
			"reply_source": bal_res.get("reply_source"),
			"detected_intent": bal_res.get("intent"),
			"simulated_reply": bal_res.get("reply")
		}

	# 3. Check interactive expense
	expense_res = process_expense_interactive(
		text=clean_text,
		sender_phone=norm_phone,
		sender_name=sender_name,
		contact_rule=contact_rule,
		hub=hub
	)
	if expense_res:
		return {
			"status": "ok",
			"mode": "Simulation",
			"reply_source": expense_res.get("reply_source"),
			"detected_intent": expense_res.get("intent"),
			"simulated_reply": expense_res.get("reply")
		}

	# 4. Check Gemini AI
	enable_ai = cint(hub.enable_ai_reply if hub else 0)
	ai_api_key = hub.get_password("ai_api_key", raise_exception=False) if (hub and hasattr(hub, "get_password")) else None
	if enable_ai and ai_api_key:
		ai_res = call_ai_api(
			user_message=clean_text,
			provider="Gemini",
			api_key=ai_api_key,
			model=hub.ai_model if hub else "Gemini 3.5 Flash Lite",
			system_prompt=hub.ai_system_prompt if hub else None
		)
		if ai_res.get("status") == "ok":
			return {
				"status": "ok",
				"mode": "Simulation",
				"reply_source": "Gemini AI",
				"detected_intent": "General Inquiry",
				"simulated_reply": ai_res.get("reply")
			}

	return {
		"status": "ok",
		"mode": "Simulation",
		"reply_source": "Fallback Template",
		"detected_intent": "Help Menu",
		"simulated_reply": generate_local_fallback_reply(clean_text)
	}
