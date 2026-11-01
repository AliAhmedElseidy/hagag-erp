"""Run from frappe-bench with its Python environment. Never prints credentials or session content."""
import hashlib
import json
import frappe
import requests

frappe.init(site="erp.local", sites_path="/home/frappe/frappe-bench/sites")
frappe.connect()
try:
    frappe.set_user("Administrator")
    hub = frappe.get_single("Elsaidy WhatsApp Hub")
    token = hub.get_password("api_token", raise_exception=False)
    health = requests.get((hub.baileys_url or "http://wa-baileys:3000").rstrip('/') + '/status',
        headers={"x-api-token": token or ""}, timeout=15)
    status = health.json()
    result = {
        "api_token_configured": bool(token),
        "api_auth_status": health.status_code,
        "runtime_status": {k: status.get(k) for k in ["engine_state", "connected", "bot_phone", "last_disconnect_reason", "uptime_seconds"]},
        "settings": {k: hub.get(k) for k in ["bot_mode", "auto_reply_enabled", "enable_ai_reply", "ai_provider", "ai_model", "allow_unregistered_direct", "allow_unregistered_groups"]},
        "ai_key_configured": bool(hub.get_password("ai_api_key", raise_exception=False)),
        "contacts": [{"phone": r.phone_number, "lid": r.get("whatsapp_lid"), "active": r.is_active,
                      "can_record_expenses": r.can_record_expenses} for r in hub.allowed_direct_contacts],
        "group_count": len(hub.allowed_groups),
        "log_fields": [f.fieldname for f in frappe.get_meta("Elsaidy WhatsApp Log").fields],
        "logs_today": frappe.db.sql("""SELECT direction,status,delivery_status,count(*) AS count
            FROM `tabElsaidy WhatsApp Log` WHERE creation >= CURDATE()
            GROUP BY direction,status,delivery_status""", as_dict=True),
        "db_connected": frappe.db.sql("SELECT 1")[0][0] == 1,
        "cache_connected": bool(frappe.cache.ping()),
    }
    print(json.dumps(result, default=str, ensure_ascii=False))
finally:
    frappe.db.rollback()
    frappe.destroy()
