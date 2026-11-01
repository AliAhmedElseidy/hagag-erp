"""Report provider error classification and scheduling configuration, without secret values."""
import json
import requests
import frappe

frappe.init(site='erp.local', sites_path='/home/frappe/frappe-bench/sites')
frappe.connect()
try:
    frappe.set_user('Administrator')
    hub = frappe.get_single('Elsaidy WhatsApp Hub')
    key = hub.get_password('ai_api_key', raise_exception=False)
    response = requests.post('https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent',
        headers={'x-goog-api-key': key}, json={'contents': [{'parts': [{'text': 'Reply OK'}]}]}, timeout=25)
    data = response.json()
    err = data.get('error') or {}
    print(json.dumps({'provider_http': response.status_code, 'provider_error_status': err.get('status'),
                      'provider_error_message': str(err.get('message', '')).replace(key or '[unset]', '[redacted]')[:500]}, ensure_ascii=False))
    scheduler_hooks = frappe.get_hooks('scheduler_events')
    print(json.dumps({'recovery_hook_present': 'enqueue_pending_whatsapp_messages' in str(scheduler_hooks),
                      'existing_recovery_jobs': frappe.get_all('Scheduled Job Type', filters={'method': ['like', '%whatsapp%']}, fields=['method', 'stopped', 'frequency'])},default=str))
finally:
    frappe.db.rollback()
    frappe.destroy()
