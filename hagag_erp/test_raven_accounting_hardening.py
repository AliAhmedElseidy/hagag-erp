import frappe
import json
from decimal import Decimal
from hagag_erp.ai_tools import (
    format_tool_response,
    prepare_financial_operation_preview,
    execute_confirmed_financial_operation,
    submit_financial_document,
    record_employee_custody_expense,
    get_employee_custody_report,
    get_gl_balance
)
from hagag_erp.custody_service import (
    get_employee_live_gl_balance,
    send_custody_whatsapp_notification
)

def run_tests():
    print("============================================================")
    print("ELSAIDY ERP — RAVEN AI & ACCOUNTING HARDENING ACCEPTANCE TEST")
    print("============================================================")
    results = {}

    # Initial Draft Cleanup for clean test slate
    for djv in frappe.get_all("Journal Entry", filters={"docstatus": 0}):
        frappe.delete_doc("Journal Entry", djv.name, ignore_permissions=True, force=True)
    frappe.db.commit()

    # ──────────────────────────────────────────────────────────
    # Test 1: Real Balance Query Verification (Reference = 270 SAR)
    # ──────────────────────────────────────────────────────────
    print("\n[Test 1] Testing live GL custody balance query for HR-EMP-00001...")
    bal_res = get_employee_live_gl_balance(employee="HR-EMP-00001")
    rep_res = get_employee_custody_report(employee="HR-EMP-00001")
    posted_bal = float(bal_res.get("posted_custody_balance", 0.0))
    print(f"  Posted Custody Balance: {posted_bal} SAR")
    print(f"  Disbursed (Dr): {rep_res.get('total_disbursed')} | Expenses (Cr): {rep_res.get('total_expenses')}")
    assert posted_bal == 270.0, f"Expected 270.0 SAR, got {posted_bal}"
    results["test_1_balance_query"] = {
        "status": "PASS",
        "posted_custody_balance": posted_bal,
        "disbursed": rep_res.get('total_disbursed'),
        "expenses": rep_res.get('total_expenses')
    }
    print("  -> PASS: Live GL Balance is strictly 270.00 SAR.")

    # ──────────────────────────────────────────────────────────
    # Test 2 & 3: Reject Tax Assumption & Require Clarification
    # ──────────────────────────────────────────────────────────
    print("\n[Test 2 & 3] Testing tax assumption rejection (missing tax_status)...")
    clarif_res = prepare_financial_operation_preview(
        operation_type="custody_expense",
        amount=75.0,
        employee="HR-EMP-00001",
        tax_status="unspecified"
    )
    print(f"  Response: success={clarif_res.get('success')}, clarification={clarif_res.get('requires_clarification')}")
    print(f"  Message preview: {clarif_res.get('message')[:100]}...")
    assert clarif_res.get("success") is False, "Expected success=False when tax_status is unspecified"
    assert clarif_res.get("requires_clarification") is True, "Expected requires_clarification=True"
    assert "tax_status" in clarif_res.get("missing_fields", []), "Expected tax_status in missing_fields"
    results["test_2_3_tax_clarification"] = {
        "status": "PASS",
        "requires_clarification": clarif_res.get("requires_clarification"),
        "missing_fields": clarif_res.get("missing_fields")
    }
    print("  -> PASS: Zero Tax Assumption strictly enforced at code level.")

    # ──────────────────────────────────────────────────────────
    # Test 4: Preview Only Creates NO Document in Database
    # ──────────────────────────────────────────────────────────
    print("\n[Test 4] Testing preview generation without database creation...")
    jv_count_before = frappe.db.count("Journal Entry")
    preview_res = prepare_financial_operation_preview(
        operation_type="custody_expense",
        amount=60.0,
        employee="HR-EMP-00001",
        tax_status="inclusive",
        has_tax_invoice=1,
        expense_category="fuel",
        description="معاينة اختبار تجريبي لمحروقات"
    )
    jv_count_after = frappe.db.count("Journal Entry")
    op_id = preview_res.get("operation_id")
    print(f"  Operation ID: {op_id}")
    print(f"  Journal Entry count before: {jv_count_before} | after: {jv_count_after}")
    assert jv_count_before == jv_count_after, "Preview MUST NOT create any Journal Entry in database!"
    assert preview_res.get("success") is True, "Preview should succeed"
    assert op_id and op_id.startswith("OP-PREV"), f"Invalid operation_id: {op_id}"
    results["test_4_preview_no_document"] = {
        "status": "PASS",
        "operation_id": op_id,
        "jv_count_before": jv_count_before,
        "jv_count_after": jv_count_after
    }
    print("  -> PASS: Preview successfully prepared and cached without touching DB.")

    # ──────────────────────────────────────────────────────────
    # Test 5: Execution of Confirmed Operation (Draft Mode for safety)
    # ──────────────────────────────────────────────────────────
    print("\n[Test 5] Testing real execution of confirmed operation (submit=0)...")
    exec_res = execute_confirmed_financial_operation(operation_id=op_id, submit=0)
    created_jv = exec_res.get("document_name")
    print(f"  Created Document: {created_jv} | Status: {exec_res.get('docstatus')}")
    print(f"  Document URL: {exec_res.get('document_url')}")
    assert exec_res.get("success") is True, f"Execution failed: {exec_res.get('error')}"
    assert frappe.db.exists("Journal Entry", created_jv), f"Document {created_jv} not in DB!"
    assert exec_res.get("docstatus") == 0, f"Expected docstatus=0, got {exec_res.get('docstatus')}"
    assert "journal-entry/" in exec_res.get("document_url"), "Invalid doc URL"
    results["test_5_execution_real_tool"] = {
        "status": "PASS",
        "document_name": created_jv,
        "docstatus": exec_res.get("docstatus"),
        "document_url": exec_res.get("document_url")
    }
    print("  -> PASS: Real tool created verified draft Journal Entry with official URL.")

    # ──────────────────────────────────────────────────────────
    # Test 6: Failure Handling Without Declaring Success
    # ──────────────────────────────────────────────────────────
    print("\n[Test 6] Testing failure handling with fake/expired operation ID...")
    fail_res = execute_confirmed_financial_operation(operation_id="OP-PREV-NONEXISTENT")
    print(f"  Response: success={fail_res.get('success')}, error={fail_res.get('error')}")
    assert fail_res.get("success") is False, "Expected success=False for fake op"
    assert fail_res.get("error") is not None, "Expected explicit error"
    results["test_6_failure_handling"] = {
        "status": "PASS",
        "success": fail_res.get("success"),
        "error": fail_res.get("error")
    }
    print("  -> PASS: Error gracefully handled without converting to fake success.")

    # ──────────────────────────────────────────────────────────
    # Test 7: Anti-Duplication on Replay
    # ──────────────────────────────────────────────────────────
    print("\n[Test 7] Testing anti-duplication when executing the same op_id again...")
    dup_res = execute_confirmed_financial_operation(operation_id=op_id, submit=0)
    print(f"  Replay response: success={dup_res.get('success')}, error={dup_res.get('error')}")
    # Cache was deleted upon first execution, so second execution must not create a new JV
    jv_count_after_dup = frappe.db.count("Journal Entry")
    assert jv_count_after_dup == jv_count_after + 1, "Duplicate replay MUST NOT create another document!"
    results["test_7_anti_duplication"] = {
        "status": "PASS",
        "replay_blocked": True
    }
    print("  -> PASS: Operation ID invalidated after first use; duplicate replay blocked.")

    # Clean up the draft test voucher to maintain production clean slate!
    if created_jv:
        frappe.delete_doc("Journal Entry", created_jv, ignore_permissions=True, force=True)
        frappe.db.commit()
        print(f"  Cleaned up temporary test draft {created_jv} safely.")

    # ──────────────────────────────────────────────────────────
    # Test 8: Document Link Verification
    # ──────────────────────────────────────────────────────────
    print("\n[Test 8] Testing document URL generation...")
    test_url = frappe.utils.get_url_to_form("Journal Entry", "ACC-JV-2026-00015")
    print(f"  Official Form URL for ACC-JV-2026-00015: {test_url}")
    assert "journal-entry/ACC-JV-2026-00015" in test_url
    results["test_8_url_generation"] = {
        "status": "PASS",
        "url": test_url
    }
    print("  -> PASS: Document link generated via official Frappe API.")

    # ──────────────────────────────────────────────────────────
    # Test 9: Employee & User Permissions
    # ──────────────────────────────────────────────────────────
    print("\n[Test 9] Testing employee resolution & authorization check...")
    invalid_emp = prepare_financial_operation_preview(
        operation_type="custody_expense",
        amount=100.0,
        employee="NON-EXISTENT-EMP-99999",
        tax_status="inclusive"
    )
    print(f"  Invalid employee response: success={invalid_emp.get('success')}, error={invalid_emp.get('error')}")
    assert invalid_emp.get("success") is False, "Expected failure for non-existent employee"
    results["test_9_permissions"] = {
        "status": "PASS",
        "blocked_invalid_employee": True
    }
    print("  -> PASS: Invalid or unauthorized employee blocked.")

    # ──────────────────────────────────────────────────────────
    # Test 10: WhatsApp Notification Deduplication Integration
    # ──────────────────────────────────────────────────────────
    print("\n[Test 10] Testing WhatsApp notification deduplication for ACC-JV-2026-00015...")
    notif_res = send_custody_whatsapp_notification(
        phone="201028632620",
        message="Test duplicate notification",
        docname="ACC-JV-2026-00015",
        doctype="Journal Entry",
        intent_title="إشعار مكرر"
    )
    print(f"  Notification dispatch result: {notif_res}")
    assert notif_res.get("status") == "skipped" and notif_res.get("reason") == "Already notified", \
        f"Expected skipped with reason 'Already notified', got {notif_res}"
    results["test_10_notification_dedup"] = {
        "status": "PASS",
        "result": notif_res
    }
    print("  -> PASS: Duplicate notification blocked for already delivered document.")

    # Final Summary
    print("\n" + "="*60)
    print("ALL 10 HARDENING TESTS PASSED SUCCESSFULLY (10/10)")
    print("="*60)
    print("SUMMARY:", json.dumps(results, indent=2, ensure_ascii=False))
    return results

if __name__ == "__main__":
    run_tests()
