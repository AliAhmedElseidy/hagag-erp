"""Offline behavior tests. No Frappe site, HTTP service, or financial documents are touched."""
import importlib.util
import json
from pathlib import Path
import sys
import types
import unittest
from contextlib import nullcontext
from unittest.mock import MagicMock, patch


class Record(dict):
    def __getattr__(self, key):
        return self.get(key)

    def __setattr__(self, key, value):
        self[key] = value


class FakeDoc(Record):
    def insert(self, **kwargs):
        self.name = self.get('name') or self.message_id
        return self

    def save(self, **kwargs):
        return self

    def reload(self):
        return self


class Cache:
    def __init__(self):
        self.values = {}

    def lock(self, *args, **kwargs):
        return nullcontext()

    def get_value(self, key):
        return self.values.get(key)

    def set_value(self, key, value, **kwargs):
        self.values[key] = value

    def delete_value(self, key):
        self.values.pop(key, None)


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.cache = Cache()
        self.frappe = types.ModuleType('frappe')
        f = self.frappe
        f.whitelist = lambda **kwargs: lambda fn: fn
        f._ = lambda value: value
        f.session = Record(user='Administrator')
        f.has_permission = MagicMock(return_value=True)
        f.get_roles = lambda: ['System Manager']
        f.PermissionError = PermissionError
        f.throw = lambda message, exc=ValueError: self.raise_error(message, exc)
        f.cache = lambda: self.cache
        f.db = MagicMock()
        f.db.get_value.return_value = None
        f.db.exists.return_value = False
        f.db.sql.return_value = []
        f.logger = MagicMock()
        f.log_error = MagicMock()
        f.response = {}
        f.enqueue = MagicMock()
        self.docs = []
        def new_doc(doctype):
            doc = FakeDoc(doctype=doctype)
            self.docs.append(doc)
            return doc
        f.new_doc = new_doc
        self.hub = Record(
            bot_phone_number='201000000000', connected_phone='201000000000',
            allowed_direct_contacts=[], allowed_groups=[], bot_mode='AI Assistant Only',
            auto_reply_enabled=1, enable_ai_reply=0, allow_unregistered_direct=1,
            get_password=lambda *args, **kwargs: 'offline-token',
        )
        f.get_single = lambda name: self.hub
        utils = types.ModuleType('frappe.utils')
        utils.now_datetime = lambda: '2026-11-01 12:00:00'
        utils.today = lambda: '2026-11-01'
        utils.cint = lambda value: int(value or 0)
        utils.flt = lambda value: float(value or 0)
        self.requests = types.ModuleType('requests')
        self.requests.get = MagicMock()
        self.requests.post = MagicMock()
        self.requests.Timeout = TimeoutError
        self.requests.utils = Record(quote=lambda text: text)
        self.modules = patch.dict(sys.modules, {'frappe': f, 'frappe.utils': utils, 'requests': self.requests})
        self.modules.start()
        self.addCleanup(self.modules.stop)
        spec = importlib.util.spec_from_file_location('bridge_under_test', Path(__file__).parents[1] / 'hagag_erp/whatsapp_bridge.py')
        self.bridge = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.bridge)

    @staticmethod
    def raise_error(message, exc):
        raise exc(message)

    def payload(self, **kwargs):
        return dict(event_type='message', message_id='IN-1', remote_jid='966500000001@s.whatsapp.net',
                    sender_jid='966500000001@s.whatsapp.net', sender_phone='966500000001', text='hello', **kwargs)

    def request(self, payload, token='offline-token'):
        self.frappe.request = Record(headers={'x-api-token': token}, get_json=lambda: payload)

    def test_phone_and_device_normalization(self):
        self.assertEqual(self.bridge.normalize_phone_number('٠٥٠٠٠٠٠٠٠١'), '966500000001')
        self.assertEqual(self.bridge.canonical_jid('123:8@lid'), '123@lid')
        self.assertEqual(self.bridge.resolve_destination_jid('123456789012345'), '123456789012345@s.whatsapp.net')
        self.assertEqual(self.bridge.resolve_destination_jid('1@newsletter'), '')

    def test_fail_closed_on_missing_api_secret(self):
        self.hub.get_password = lambda *args, **kwargs: None
        self.assertEqual(self.bridge.call_baileys_api('status')['status'], 'error')
        self.requests.get.assert_not_called()
        self.request(self.payload(), '')
        self.assertEqual(self.bridge.receive_baileys_event(), {'error': 'Unauthorized'})

    def test_webhook_auth_rejects_before_database_or_enqueue(self):
        self.request(self.payload(), 'wrong')
        self.assertEqual(self.bridge.receive_baileys_event(), {'error': 'Unauthorized'})
        self.frappe.db.get_value.assert_not_called()
        self.frappe.enqueue.assert_not_called()

    def test_http_success_with_error_is_not_send_success(self):
        self.requests.post.return_value = Record(ok=True, status_code=200, json=lambda: {'status': 'error'})
        self.assertFalse(self.bridge.send_accepted(self.bridge.call_baileys_api('send', 'POST')))
        self.requests.post.return_value = Record(ok=False, status_code=500, json=lambda: {'status': 'ok', 'msg_id': 'FAKE'})
        self.assertFalse(self.bridge.send_accepted(self.bridge.call_baileys_api('send', 'POST')))
        self.assertFalse(self.bridge.send_accepted({'status': 'ok'}))

    def test_inbox_admission_persists_before_queue(self):
        events = []
        self.frappe.db.commit.side_effect = lambda: events.append('commit')
        self.frappe.enqueue.side_effect = lambda *args, **kwargs: events.append('enqueue')
        self.request(self.payload())
        self.assertEqual(self.bridge.receive_baileys_event()['status'], 'queued')
        self.assertEqual(events, ['commit', 'enqueue'])
        self.assertEqual(self.docs[0].conversation_id, '966500000001')
        self.assertEqual(json.loads(self.docs[0].inbound_payload)['message_id'], 'IN-1')

    def test_terminal_duplicate_never_enqueues_or_sends(self):
        self.frappe.db.get_value.return_value = Record(name='IN-1', status='Ignored')
        self.request(self.payload())
        self.assertEqual(self.bridge.receive_baileys_event()['status'], 'already_processed')
        self.frappe.enqueue.assert_not_called()

    def test_failed_automatic_send_never_marks_replied(self):
        self.bridge.send_baileys_reply = MagicMock(return_value={'status': 'error', 'error': 'transport down'})
        doc = FakeDoc()
        self.bridge._process_baileys_payload(self.payload(), doc)
        self.assertEqual(doc.status, 'Failed')
        self.assertEqual(doc.delivery_status, 'Delivered')  # Incoming delivery remains independent.
        self.assertEqual(len(self.docs), 0)

    def test_automatic_reply_gets_separate_outgoing_id(self):
        self.bridge.send_baileys_reply = MagicMock(return_value={'status': 'ok', 'msg_id': 'OUT-1'})
        doc = FakeDoc()
        self.bridge._process_baileys_payload(self.payload(), doc)
        self.assertEqual(doc.status, 'Replied')
        outgoing = self.docs[0]
        self.assertEqual(outgoing.message_id, 'OUT-1')
        self.assertEqual(outgoing.in_reply_to, 'IN-1')
        self.assertEqual(outgoing.delivery_status, 'Pending')
        self.assertEqual(outgoing.conversation_id, '966500000001')

    def test_human_takeover_suppresses_auto_reply_and_finishes_processing(self):
        self.cache.set_value('wa_takeover_966500000001', 1)
        self.bridge.send_baileys_reply = MagicMock()
        doc = FakeDoc()
        result = self.bridge._process_baileys_payload(self.payload(), doc)
        self.assertTrue(result['human_takeover'])
        self.assertEqual(doc.status, 'Processed')
        self.bridge.send_baileys_reply.assert_not_called()

    def test_group_takeover_does_not_use_phone_digits(self):
        self.bridge.toggle_human_takeover('120-44@g.us')
        self.assertEqual(self.cache.get_value('wa_takeover_120-44@g.us'), 1)
        self.assertIsNone(self.cache.get_value('wa_takeover_12044'))

    def test_partial_phone_match_does_not_authorize_sender(self):
        self.hub.allow_unregistered_direct = 0
        self.hub.auto_reply_enabled = 0
        self.hub.allowed_direct_contacts = [Record(is_active=1, phone_number='500000001', whatsapp_lid='')]
        payload = self.payload()
        payload['sender_phone'] = ''
        payload['sender_jid'] = '1966500000001@s.whatsapp.net'
        doc = FakeDoc()
        result = self.bridge._process_baileys_payload(payload, doc)
        self.assertEqual(result['status'], 'rejected')

    def test_delivery_receipts_are_monotonic_and_server_ack_is_only_sent(self):
        self.assertEqual(self.bridge.delivery_status_for(2), 'Sent')
        self.assertEqual(self.bridge.delivery_status_for(3), 'Delivered')
        self.assertEqual(self.bridge.delivery_status_for(0), 'Failed')
        self.assertIsNone(self.bridge.delivery_status_for(99))
        self.bridge.apply_delivery_receipt('OUT-1', 4)
        self.bridge.apply_delivery_receipt('OUT-1', 2)
        self.assertEqual(self.frappe.db.sql.call_args.args[1][0], 'Read')
        self.assertIn("direction = 'Outgoing'", self.frappe.db.sql.call_args.args[0])

    def test_receipt_webhook_uses_status_code(self):
        self.request({'event_type': 'status_update', 'message_id': 'OUT-1', 'status_code': 3})
        self.assertEqual(self.bridge.receive_baileys_event()['delivery_status'], 'Delivered')

    def test_every_gui_endpoint_checks_permissions(self):
        self.frappe.has_permission.return_value = False
        calls = {
            'get_dashboard_telemetry': (), 'get_message_center_conversations': (), 'get_conversation_thread': ('123',),
            'get_system_health_report': (), 'get_baileys_logs': (), 'simulate_whatsapp_message': ('hello',),
            'sync_all_contact_mappings_to_baileys': (), 'send_conversation_reply': ('123', 'hello'),
            'toggle_human_takeover': ('123',), 'test_ai_configuration': (), 'send_test_whatsapp_message': ('123', 'hello'),
            'wipe_baileys_session': (), 'heal_baileys_session': ('123',),
        }
        for name, args in calls.items():
            with self.subTest(name=name), self.assertRaises(PermissionError):
                getattr(self.bridge, name)(*args)

    def test_thread_fetches_newest_page_then_returns_chronological_order(self):
        self.frappe.db.sql.return_value = [Record(message_id='NEW'), Record(message_id='OLD')]
        result = self.bridge.get_conversation_thread('966500000001', -1)
        self.assertEqual([r.message_id for r in result['messages']], ['OLD', 'NEW'])
        self.assertIn('ORDER BY creation DESC', self.frappe.db.sql.call_args.args[0])
        self.assertEqual(self.frappe.db.sql.call_args.args[1][-1], 1)

    def test_worker_never_replays_uncertain_processing_record(self):
        self.frappe.get_doc = lambda *args: FakeDoc(status='Processing')
        self.bridge._process_baileys_payload = MagicMock()
        self.bridge.process_baileys_message('IN-1')
        self.bridge._process_baileys_payload.assert_not_called()


if __name__ == '__main__':
    unittest.main()
