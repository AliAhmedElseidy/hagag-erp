"""Exercise live Inbox SQL with temporary log rows, rolled back. Never sends or touches accounting."""
import json
import uuid
import frappe

frappe.init(site='erp.local', sites_path='/home/frappe/frappe-bench/sites')
frappe.connect()
try:
    frappe.set_user('Administrator')
    from hagag_erp.whatsapp_bridge import get_conversation_thread
    token = 'WA-SQL-CHECK-' + uuid.uuid4().hex
    phone = '19999999999'
    group = '999999999999999-1@g.us'
    for suffix, is_group in [('DIRECT', 0), ('GROUP', 1)]:
        doc = frappe.new_doc('Elsaidy WhatsApp Log')
        doc.message_id = token + suffix
        doc.direction = 'Incoming'
        doc.sender_phone = phone
        doc.is_group = is_group
        doc.group_jid = group if is_group else ''
        doc.conversation_id = group if is_group else phone
        doc.status = 'Processed'
        doc.delivery_status = 'Delivered'
        doc.message_text = 'Temporary SQL integration record; never sent'
        doc.insert(ignore_permissions=True)
    direct = get_conversation_thread(phone)['messages']
    grouped = get_conversation_thread(group)['messages']
    assert any(row.message_id == token + 'DIRECT' for row in direct)
    assert all(row.message_id != token + 'GROUP' for row in direct)
    assert any(row.message_id == token + 'GROUP' for row in grouped)
    assert all(row.message_id != token + 'DIRECT' for row in grouped)
    frappe.db.rollback()
    assert not frappe.db.exists('Elsaidy WhatsApp Log', {'message_id': token + 'DIRECT'})
    assert not frappe.db.exists('Elsaidy WhatsApp Log', {'message_id': token + 'GROUP'})
    print(json.dumps({'inbox_sql_group_isolation': True, 'temporary_records_rolled_back': True, 'outbound_sends': 0, 'accounting_writes': 0}))
finally:
    frappe.db.rollback()
    frappe.destroy()
