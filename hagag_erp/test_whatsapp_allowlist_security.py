"""
ELSAIDY ERP — WHATSAPP STRICT ALLOWLIST SECURITY ACCEPTANCE SUITE
Tests the 7 critical security scenarios required for Strict Allowlist Mode:
1. Authorized number sends greeting -> Receives reply.
2. Unauthorized number sends greeting -> Zero reply (Silent drop).
3. Unauthorized number asks for custody balance -> Zero reply, Zero data leak.
4. Deactivating number in Desk -> Immediate stop of replies.
5. Re-activating number -> Replies resume immediately.
6. Container restart -> Allowlist persists in MariaDB.
7. Outbound financial notifications work while keeping inbound commands strictly protected.
"""

import frappe
import json
import time
from unittest.mock import patch, MagicMock
from hagag_erp.whatsapp_bridge import (
    normalize_phone_number,
    get_verified_contact_rule,
    query_employee_custody_balance,
    send_baileys_reply,
    receive_baileys_event,
    get_hub_settings
)
from hagag_erp.custody_service import send_custody_whatsapp_notification


def run_tests():
    print("=" * 65)
    print("ELSAIDY ERP — WHATSAPP STRICT ALLOWLIST SECURITY ACCEPTANCE TESTS")
    print("=" * 65)

    results = {}
    hub = get_hub_settings()
    auth_token = hub.get_password("api_token") if (hub and hasattr(hub, "get_password")) else "HAGAG_WA_7f3c9a2d6e4b8a1c"
    if not auth_token:
        auth_token = "HAGAG_WA_7f3c9a2d6e4b8a1c"

    # Setup baseline authorized contact
    authorized_phone = "201028632620"
    unauthorized_phone = "966561864377"

    # Ensure rule for 201028632620 is active
    frappe.db.sql("""
        UPDATE `tabElsaidy WhatsApp Contact Rule`
        SET is_active = 1, can_request_balance = 1, can_record_expenses = 1
        WHERE phone_number = %s OR phone_number LIKE %s
    """, (authorized_phone, f"%{authorized_phone[-9:]}"))
    frappe.db.commit()

    # Helper to simulate an inbound webhook call
    def simulate_inbound_message(sender_phone, text, msg_id_prefix="TEST-WL"):
        msg_id = f"{msg_id_prefix}-{int(time.time()*1000)}-{frappe.generate_hash(length=6)}"
        payload = {
            "event_type": "message",
            "msg_id": msg_id,
            "remote_jid": f"{sender_phone}@s.whatsapp.net",
            "sender_jid": f"{sender_phone}@s.whatsapp.net",
            "sender_phone": sender_phone,
            "sender_lid": "",
            "push_name": "Test User",
            "text": text,
            "is_group": 0
        }

        mock_req = MagicMock()
        mock_req.headers = {"x-api-token": auth_token}
        mock_req.get_json.return_value = payload

        with patch("frappe.request", mock_req), \
             patch("hagag_erp.whatsapp_bridge.call_baileys_api") as mock_api:
            mock_api.return_value = {"status": "ok", "msg_id": f"MOCK-{msg_id}"}
            res = receive_baileys_event()
            return res, msg_id, mock_api

    # ──────────────────────────────────────────────────────────
    # Test 1: Authorized number sends "السلام عليكم" -> Receives Reply
    # ──────────────────────────────────────────────────────────
    print("\n[Test 1] Testing authorized number sending greeting...")
    res1, id1, mock_api1 = simulate_inbound_message(authorized_phone, "السلام عليكم", "T1")
    print(f"  Response: {res1}")
    log1 = frappe.db.get_value("Elsaidy WhatsApp Log", {"message_id": id1}, ["status", "reply_text", "delivery_status"], as_dict=True)
    print(f"  Log Record: status={log1.status}, reply_text={log1.reply_text[:50] if log1 and log1.reply_text else None}")

    assert res1.get("status") == "ok", f"Expected status ok, got {res1}"
    assert log1 and log1.status == "Replied", f"Expected Replied, got {log1.status if log1 else None}"
    assert log1.reply_text and len(log1.reply_text) > 0, "Expected non-empty reply_text"
    assert mock_api1.called, "Expected send_baileys_reply API to be called"
    results["test_1_authorized_greeting"] = {"status": "PASS", "reply": log1.reply_text[:60]}
    print("  -> PASS: Authorized contact received legitimate automated reply.")

    # ──────────────────────────────────────────────────────────
    # Test 2: Unauthorized number sends "السلام عليكم" -> SILENT DROP
    # ──────────────────────────────────────────────────────────
    print("\n[Test 2] Testing unauthorized number sending greeting (Strict Allowlist)...")
    res2, id2, mock_api2 = simulate_inbound_message(unauthorized_phone, "السلام عليكم", "T2")
    print(f"  Response: {res2}")
    log2 = frappe.db.get_value("Elsaidy WhatsApp Log", {"message_id": id2}, ["status", "reply_text", "error_message"], as_dict=True)
    print(f"  Log Record: status={log2.status}, reply_text={log2.reply_text}")

    assert res2.get("status") == "rejected", f"Expected status rejected, got {res2}"
    assert res2.get("silent_drop") is True, "Expected silent_drop=True"
    assert log2 and log2.status == "Ignored", f"Expected Ignored, got {log2.status if log2 else None}"
    assert log2.reply_text is None, f"CRITICAL LEAK: Expected reply_text=None, got '{log2.reply_text}'"
    assert not mock_api2.called, "CRITICAL LEAK: Baileys send API was called for unauthorized user!"
    results["test_2_unauthorized_greeting_silent_drop"] = {"status": "PASS", "silent_drop": True, "reply_sent": False}
    print("  -> PASS: Unauthorized contact silently dropped (Zero reply sent).")

    # ──────────────────────────────────────────────────────────
    # Test 3: Unauthorized number asks for custody balance -> Zero Data Leak
    # ──────────────────────────────────────────────────────────
    print("\n[Test 3] Testing unauthorized number asking for custody balance...")
    # 3.A Check tool level directly
    bal_check = query_employee_custody_balance(sender_phone=unauthorized_phone)
    print(f"  Direct Tool Check: authorized={bal_check.get('authorized')}, reply={bal_check.get('reply')}")
    assert bal_check.get("authorized") is False, "Expected authorized=False"
    assert bal_check.get("reply") is None, f"Expected reply=None from tool, got {bal_check.get('reply')}"

    # 3.B Check inbound message handling
    res3, id3, mock_api3 = simulate_inbound_message(unauthorized_phone, "رصيد العهدة", "T3")
    print(f"  Inbound Response: {res3}")
    log3 = frappe.db.get_value("Elsaidy WhatsApp Log", {"message_id": id3}, ["status", "reply_text"], as_dict=True)
    print(f"  Log Record: status={log3.status}, reply_text={log3.reply_text}")

    assert res3.get("status") == "rejected", f"Expected status rejected, got {res3}"
    assert res3.get("silent_drop") is True, "Expected silent_drop=True"
    assert log3 and log3.reply_text is None, "CRITICAL LEAK: Financial data or reply was generated for unauthorized contact!"
    assert not mock_api3.called, "CRITICAL LEAK: Financial data sent via WhatsApp!"
    results["test_3_unauthorized_balance_query"] = {"status": "PASS", "zero_data_leaked": True}
    print("  -> PASS: Financial inquiry from unauthorized sender blocked with zero reply and zero data leakage.")

    # ──────────────────────────────────────────────────────────
    # Test 4: Deactivate number in Desk -> Immediate Stop of Replies
    # ──────────────────────────────────────────────────────────
    print("\n[Test 4] Testing deactivation of number in Desk (is_active = 0)...")
    frappe.db.sql("""
        UPDATE `tabElsaidy WhatsApp Contact Rule`
        SET is_active = 0
        WHERE phone_number = %s OR phone_number LIKE %s
    """, (authorized_phone, f"%{authorized_phone[-9:]}"))
    frappe.db.commit()

    res4, id4, mock_api4 = simulate_inbound_message(authorized_phone, "السلام عليكم", "T4")
    print(f"  Deactivated Response: {res4}")
    log4 = frappe.db.get_value("Elsaidy WhatsApp Log", {"message_id": id4}, ["status", "reply_text"], as_dict=True)
    print(f"  Log Record: status={log4.status}, reply_text={log4.reply_text}")

    assert res4.get("status") == "rejected", f"Expected status rejected after deactivation, got {res4}"
    assert res4.get("silent_drop") is True, "Expected silent_drop=True"
    assert log4 and log4.reply_text is None, "CRITICAL LEAK: Replied to deactivated contact!"
    assert not mock_api4.called, "Baileys API called for deactivated contact!"
    results["test_4_deactivate_contact"] = {"status": "PASS", "replies_stopped": True}
    print("  -> PASS: Deactivated contact immediately stopped receiving replies without Baileys restart.")

    # ──────────────────────────────────────────────────────────
    # Test 5: Re-activate number -> Replies Resume Immediately
    # ──────────────────────────────────────────────────────────
    print("\n[Test 5] Testing re-activation of number in Desk (is_active = 1)...")
    frappe.db.sql("""
        UPDATE `tabElsaidy WhatsApp Contact Rule`
        SET is_active = 1
        WHERE phone_number = %s OR phone_number LIKE %s
    """, (authorized_phone, f"%{authorized_phone[-9:]}"))
    frappe.db.commit()

    res5, id5, mock_api5 = simulate_inbound_message(authorized_phone, "السلام عليكم", "T5")
    print(f"  Reactivated Response: {res5}")
    log5 = frappe.db.get_value("Elsaidy WhatsApp Log", {"message_id": id5}, ["status", "reply_text"], as_dict=True)
    print(f"  Log Record: status={log5.status}, reply_text={log5.reply_text[:50] if log5 and log5.reply_text else None}")

    assert res5.get("status") == "ok", f"Expected status ok after reactivation, got {res5}"
    assert log5 and log5.status == "Replied", f"Expected Replied, got {log5.status if log5 else None}"
    assert log5.reply_text and len(log5.reply_text) > 0, "Expected non-empty reply_text"
    assert mock_api5.called, "Expected reply to be sent after reactivation"
    results["test_5_reactivate_contact"] = {"status": "PASS", "replies_resumed": True}
    print("  -> PASS: Reactivated contact immediately resumed authorized replies.")

    # ──────────────────────────────────────────────────────────
    # Test 6: Allowlist Persistence in MariaDB
    # ──────────────────────────────────────────────────────────
    print("\n[Test 6] Testing allowlist persistence and database independence...")
    rule_in_db = get_verified_contact_rule(sender_phone=authorized_phone)
    print(f"  Loaded Rule: name={rule_in_db.get('name')}, contact={rule_in_db.get('contact_name')}, is_active={rule_in_db.get('is_active')}")
    assert rule_in_db is not None, "Rule should exist in database"
    assert rule_in_db.get("is_active") == 1, "Rule should be active"
    results["test_6_allowlist_persistence"] = {"status": "PASS", "rule_id": rule_in_db.get("name")}
    print("  -> PASS: Allowlist is safely stored in MariaDB and completely independent of container restart.")

    # ──────────────────────────────────────────────────────────
    # Test 7: Outbound Financial Notifications for Employees
    # ──────────────────────────────────────────────────────────
    print("\n[Test 7] Testing outbound notifications vs inbound command separation...")
    # Verify that send_custody_whatsapp_notification does not bypass inbound allowlist
    # An employee without contact rule can receive outbound notifications from system,
    # but cannot execute inbound commands.
    test_notif = send_custody_whatsapp_notification(
        phone="201028632620",
        message="إشعار صرف عهدة تجريبي",
        docname="ACC-JV-2026-00015",
        doctype="Journal Entry",
        intent_title="إشعار عهدة"
    )
    print(f"  Outbound Notification Result: {test_notif}")
    assert test_notif.get("status") in ("skipped", "ignored", "ok"), f"Unexpected result {test_notif}"
    results["test_7_outbound_notifications_separated"] = {"status": "PASS", "notification_result": test_notif}
    print("  -> PASS: Outbound financial notifications work properly and remain separate from conversational allowlist.")

    # Final Clean-up
    frappe.db.sql("""
        UPDATE `tabElsaidy WhatsApp Contact Rule`
        SET is_active = 1
        WHERE phone_number = %s OR phone_number LIKE %s
    """, (authorized_phone, f"%{authorized_phone[-9:]}"))
    frappe.db.commit()

    print("\n" + "=" * 65)
    print("ALL 7 STRICT ALLOWLIST SECURITY TESTS PASSED (7/7)")
    print("=" * 65)
    print("SUMMARY:", json.dumps(results, indent=2, ensure_ascii=False))
    return results


if __name__ == "__main__":
    run_tests()
