"""Read-only live checks plus a reversible takeover check on an unused synthetic identity."""
import json
import frappe

frappe.init(site='erp.local', sites_path='/home/frappe/frappe-bench/sites')
frappe.connect()
try:
    frappe.set_user('Administrator')
    from hagag_erp import whatsapp_bridge as bridge
    checks = {}
    for name, kwargs in [
        ('get_dashboard_telemetry', {}),
        ('get_message_center_conversations', {'limit': 10}),
        ('get_conversation_thread', {'target_id': '966569589664', 'limit': 10}),
        ('get_system_health_report', {}),
        ('get_baileys_logs', {'limit': 5}),
        ('get_frappe_whatsapp_logs', {'limit': 5}),
    ]:
        try:
            result = getattr(bridge, name)(**kwargs)
            checks[name] = {'status': result.get('status'),
                            'count': len(result.get('messages', result.get('conversations', result.get('logs', []))))}
            if name == 'get_dashboard_telemetry':
                checks[name].update(connected=result.get('whatsapp_connected'), metrics=result.get('transport_metrics'))
            if name == 'get_system_health_report':
                checks[name]['diagnostics'] = result.get('server_diagnostics')
        except Exception as exc:
            checks[name] = {'error': type(exc).__name__, 'message': str(exc)[:160]}
    test_identity = '000000000000001@lid'
    bridge.toggle_human_takeover(test_identity, enabled=1)
    checks['takeover_enable'] = bool(frappe.cache.get_value('wa_takeover_' + test_identity))
    bridge.toggle_human_takeover(test_identity, enabled=0)
    checks['takeover_disable'] = not bool(frappe.cache.get_value('wa_takeover_' + test_identity))
    result = bridge.test_ai_configuration(prompt='رد بكلمة واحدة: جاهز')
    checks['ai_provider'] = {'status': result.get('status'), 'fallback_used': result.get('fallback_used'), 'latency_ms': result.get('latency_ms')}
    checks['recovery_job_configured'] = bool(frappe.db.exists('Scheduled Job Type', {'method': 'hagag_erp.whatsapp_bridge.enqueue_pending_whatsapp_messages'}))
    frappe.set_user('Guest')
    try:
        bridge.get_message_center_conversations()
        checks['guest_inbox_denied'] = False
    except frappe.PermissionError:
        checks['guest_inbox_denied'] = True
    print(json.dumps(checks, default=str, ensure_ascii=False))
finally:
    frappe.db.rollback()
    frappe.destroy()
