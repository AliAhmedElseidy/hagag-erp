# -*- coding: utf-8 -*-
"""
Elsaidy ERP - ZATCA & Contracting Isolated Test Suite
=====================================================
Runs exclusively in isolated test site (erp_test.local).
Verifies:
1. Fuel pending review (1520) and pre-submit hook blocking.
2. Heavy machinery diesel recoverable VAT (1510).
3. Restricted vehicle VAT exclusion and expense capitalization.
4. Exclusive vs Inclusive calculation precision (0.01 SAR).
5. Atomic Idempotency (deduplication vs distinct requests).
6. Contracting IPC progress billing & retention tax base.
"""

from decimal import Decimal
import frappe
from frappe import _

from hagag_erp.tax_engine import (
    evaluate_vat_eligibility_and_split,
    calculate_ipc_tax_breakdown,
    validate_balanced_entry,
    round_currency
)
from hagag_erp.idempotency import (
    generate_operation_id,
    get_existing_operation
)
from hagag_erp.ai_tools import (
    create_draft_journal_entry,
    create_custody_settlement_entry,
    create_contractor_purchase_invoice
)


def run_all_tests():
    """
    Master runner for all ZATCA and contracting tests.
    """
    print("=" * 60)
    print(f"🚀 Starting Elsaidy ERP ZATCA Isolated Test Suite on site: {frappe.local.site}")
    print("=" * 60)

    # Protection: ensure we are NOT accidentally running on erp.local
    if frappe.local.site == "erp.local":
        raise frappe.PermissionError("CRITICAL SAFETY HALT: Tests cannot be executed on production site 'erp.local'!")

    results = []

    def log_result(test_name, passed, details=""):
        status = "PASSED ✅" if passed else "FAILED ❌"
        results.append({"name": test_name, "passed": passed, "details": details})
        print(f"[{status}] {test_name}: {details}")

    def find_account_line(lines_dict, code):
        for acc_name, val in lines_dict.items():
            if str(code) in acc_name:
                return val
        return None

    # Ensure accounts exist on test site
    comp = frappe.db.get_single_value("Global Defaults", "default_company") or "ركن سبل الافق"
    _ensure_test_accounts(comp)

    # -------------------------------------------------------------
    # Test 1: Fuel 230 SAR Inclusive without vehicle type -> 1520 & Submit Block
    # -------------------------------------------------------------
    try:
        t1_op = "TEST-FUEL-PENDING-001"
        res1 = create_draft_journal_entry(
            company=comp,
            debit_account="5120 - مصروف الوقود والمحروقات - Rkn",
            credit_account="1110 - نقد - Rkn",
            amount=230.00,
            amount_basis="inclusive",
            user_remark="فاتورة بنزين محطة وقود بدون تحديد المركبة",
            operation_id=t1_op
        )
        assert res1["status"] == "success", f"Creation failed: {res1}"
        je1 = frappe.get_doc("Journal Entry", res1["journal_entry"])
        assert je1.custom_tax_review_status == "قيد المراجعة الضريبية", f"Expected 'قيد المراجعة الضريبية', got '{je1.custom_tax_review_status}'"

        # Check account rows
        lines1 = {row.account: (row.debit_in_account_currency, row.credit_in_account_currency) for row in je1.accounts}
        assert find_account_line(lines1, "5120") == (200.0, 0.0), f"5120 debit incorrect: {lines1}"
        assert find_account_line(lines1, "1520") == (30.0, 0.0), f"1520 debit incorrect: {lines1}"
        assert find_account_line(lines1, "1110") == (0.0, 230.0), f"1110 credit incorrect: {lines1}"

        # Test pre-submit hook: must raise ValidationError
        submit_blocked = False
        try:
            je1.submit()
        except frappe.ValidationError:
            submit_blocked = True
        except Exception as ex:
            submit_blocked = True
            print(f"   (Hook caught with {type(ex).__name__})")

        assert submit_blocked, "Pre-submit hook FAILED to block submission of pending review document!"
        log_result("Test 1: Fuel without vehicle type routes to 1520 and blocks submission", True, f"Doc: {je1.name}, 5120=200, 1520=30, blocked=True")
    except Exception as e:
        log_result("Test 1: Fuel without vehicle type routes to 1520 and blocks submission", False, str(e))

    # -------------------------------------------------------------
    # Test 2: Diesel 230 SAR for Site Heavy Machinery + Valid Tax Invoice -> 1510
    # -------------------------------------------------------------
    try:
        t2_op = "TEST-HEAVY-DIESEL-002"
        res2 = create_draft_journal_entry(
            company=comp,
            debit_account="5120 - مصروف الوقود والمحروقات - Rkn",
            credit_account="1110 - نقد - Rkn",
            amount=230.00,
            amount_basis="inclusive",
            usage_type="commercial_equipment",
            has_valid_tax_invoice=True,
            user_remark="ديزل بوكلين وحفار الموقع بفاتورة ضريبية إلكترونية ZATCA",
            operation_id=t2_op
        )
        assert res2["status"] == "success", f"Creation failed: {res2}"
        je2 = frappe.get_doc("Journal Entry", res2["journal_entry"])
        assert je2.custom_tax_review_status == "مكتمل ومطابق", f"Expected 'مكتمل ومطابق', got '{je2.custom_tax_review_status}'"

        lines2 = {row.account: (row.debit_in_account_currency, row.credit_in_account_currency) for row in je2.accounts}
        assert find_account_line(lines2, "5120") == (200.0, 0.0), f"5120 debit incorrect: {lines2}"
        assert find_account_line(lines2, "1510") == (30.0, 0.0), f"1510 debit incorrect: {lines2}"
        assert find_account_line(lines2, "1110") == (0.0, 230.0), f"1110 credit incorrect: {lines2}"

        log_result("Test 2: Heavy machinery diesel routes to 1510 recoverable VAT", True, f"Doc: {je2.name}, 5120=200, 1510=30")
    except Exception as e:
        log_result("Test 2: Heavy machinery diesel routes to 1510 recoverable VAT", False, str(e))

    # -------------------------------------------------------------
    # Test 3: Fuel 230 SAR for Restricted Vehicle -> Capitalize to Expense
    # -------------------------------------------------------------
    try:
        t3_op = "TEST-RESTRICTED-CAR-003"
        res3 = create_draft_journal_entry(
            company=comp,
            debit_account="5120 - مصروف الوقود والمحروقات - Rkn",
            credit_account="1110 - نقد - Rkn",
            amount=230.00,
            amount_basis="inclusive",
            usage_type="restricted_vehicle",
            tax_treatment_policy="capitalize_to_expense",
            user_remark="بنزين سيارة خاصة للمدير العام",
            operation_id=t3_op
        )
        assert res3["status"] == "success", f"Creation failed: {res3}"
        je3 = frappe.get_doc("Journal Entry", res3["journal_entry"])
        assert je3.custom_tax_review_status == "مستبعد من الاسترداد الضريبي", f"Expected 'مستبعد من الاسترداد الضريبي', got '{je3.custom_tax_review_status}'"

        lines3 = {row.account: (row.debit_in_account_currency, row.credit_in_account_currency) for row in je3.accounts}
        assert find_account_line(lines3, "5120") == (230.0, 0.0), f"5120 must be 230.0 capitalized, got {lines3}"
        assert find_account_line(lines3, "1510") is None, "Restricted vehicle must NOT touch 1510!"

        log_result("Test 3: Restricted passenger car capitalizes VAT to expense", True, f"Doc: {je3.name}, 5120=230 (VAT capitalized), 1510=0")
    except Exception as e:
        log_result("Test 3: Restricted passenger car capitalizes VAT to expense", False, str(e))

    # -------------------------------------------------------------
    # Test 4: Exclusive Amount Precision (230 SAR Exclusive -> 264.50 SAR Gross)
    # -------------------------------------------------------------
    try:
        split_ex = evaluate_vat_eligibility_and_split(
            amount=230.00,
            account_code="5150 - مواد ومهمات تشغيل المشاريع - Rkn",
            is_taxable=True,
            amount_basis="exclusive",
            usage_type="commercial_equipment",
            has_valid_tax_invoice=True,
            company=comp
        )
        assert split_ex["net_expense"] == Decimal("230.00"), f"Expected 230.00 net, got {split_ex['net_expense']}"
        assert split_ex["tax_eligible"] == Decimal("34.50"), f"Expected 34.50 tax, got {split_ex['tax_eligible']}"
        assert split_ex["gross_amount"] == Decimal("264.50"), f"Expected 264.50 gross, got {split_ex['gross_amount']}"

        log_result("Test 4: Exclusive amount Decimal calculation", True, "230.00 net + 34.50 VAT = 264.50 gross")
    except Exception as e:
        log_result("Test 4: Exclusive amount Decimal calculation", False, str(e))

    # -------------------------------------------------------------
    # Test 5: Atomic Idempotency (Retry returns existing doc; new intention creates new doc)
    # -------------------------------------------------------------
    try:
        idempotency_key = "IDEMP-TEST-KEY-999"

        # First Call
        first_call = create_draft_journal_entry(
            company=comp,
            debit_account="5150 - مواد ومهمات تشغيل المشاريع - Rkn",
            credit_account="1110 - نقد - Rkn",
            amount=500.00,
            amount_basis="inclusive",
            user_remark="شراء أسمنت ومواد أولية",
            operation_id=idempotency_key
        )
        doc1_name = first_call["journal_entry"]

        # Second Call with EXACT same operation_id (Retry)
        retry_call = create_draft_journal_entry(
            company=comp,
            debit_account="5150 - مواد ومهمات تشغيل المشاريع - Rkn",
            credit_account="1110 - نقد - Rkn",
            amount=500.00,
            amount_basis="inclusive",
            user_remark="شراء أسمنت ومواد أولية",
            operation_id=idempotency_key
        )
        doc2_name = retry_call.get("journal_entry") or retry_call.get("document_name")
        assert doc1_name == doc2_name, f"Idempotency retry created different doc! ({doc1_name} vs {doc2_name})"
        assert retry_call.get("is_retry") is True, "Expected is_retry=True on duplicate operation_id"

        # Third Call with DIFFERENT operation_id (New Intention)
        new_key = "IDEMP-TEST-KEY-1000"
        distinct_call = create_draft_journal_entry(
            company=comp,
            debit_account="5150 - مواد ومهمات تشغيل المشاريع - Rkn",
            credit_account="1110 - نقد - Rkn",
            amount=500.00,
            amount_basis="inclusive",
            user_remark="شراء أسمنت ومواد أولية (طلب مستقل جديد)",
            operation_id=new_key
        )
        doc3_name = distinct_call["journal_entry"]
        assert doc3_name != doc1_name, f"New intention should create distinct doc! Got same doc {doc1_name}"

        log_result("Test 5: Atomic idempotency prevents duplicate docs and allows distinct requests", True, f"Doc1={doc1_name}, Retry returned Doc1, NewOp created {doc3_name}")
    except Exception as e:
        log_result("Test 5: Atomic idempotency prevents duplicate docs and allows distinct requests", False, str(e))

    # -------------------------------------------------------------
    # Test 6: Contracting IPC Progress Billing (Private vs Government & Retention Rule)
    # -------------------------------------------------------------
    try:
        # Private contract: 100k work, 10k retention (10%)
        # Tax base must be 100k, VAT must be 15k, Retention does NOT reduce tax base!
        ipc_priv = calculate_ipc_tax_breakdown(
            work_completed_amount=100000.00,
            retention_rate_pct=10.0,
            advance_deduction_amount=0.00,
            contract_type="عقد تجاري خاص"
        )
        assert ipc_priv["tax_base"] == Decimal("100000.00"), f"Expected 100k tax base, got {ipc_priv['tax_base']}"
        assert ipc_priv["vat_amount"] == Decimal("15000.00"), f"Expected 15k VAT, got {ipc_priv['vat_amount']}"
        assert ipc_priv["retention_amount"] == Decimal("10000.00"), f"Expected 10k retention, got {ipc_priv['retention_amount']}"
        assert ipc_priv["net_payable"] == Decimal("105000.00"), f"Expected 105k net payable (100k - 10k + 15k), got {ipc_priv['net_payable']}"
        assert ipc_priv["time_of_supply_rule"] == "certification_date", "Private contract time of supply must be certification date"

        # Government contract (منصة اعتماد): Time of supply is payment / approval date
        ipc_gov = calculate_ipc_tax_breakdown(
            work_completed_amount=100000.00,
            retention_rate_pct=10.0,
            advance_deduction_amount=0.00,
            contract_type="عقد حكومي منصة اعتماد"
        )
        assert ipc_gov["time_of_supply_rule"] == "payment_date", "Government contract time of supply must be payment date"

        log_result("Test 6: Contracting IPC retention does not reduce tax base and respects contract type", True, "Tax base=100k, VAT=15k, Retention=10k, Net=105k")
    except Exception as e:
        log_result("Test 6: Contracting IPC retention does not reduce tax base and respects contract type", False, str(e))

    # -------------------------------------------------------------
    # Test Summary
    # -------------------------------------------------------------
    total_tests = len(results)
    passed_tests = sum(1 for r in results if r["passed"])
    failed_tests = total_tests - passed_tests

    print("\n" + "=" * 60)
    print(f"📊 TEST EXECUTION SUMMARY ({passed_tests}/{total_tests} PASSED)")
    print("=" * 60)
    for r in results:
        status_symbol = "✅" if r["passed"] else "❌"
        print(f" {status_symbol} {r['name']}")
    print("=" * 60)

    if failed_tests > 0:
        raise frappe.ValidationError(f"{failed_tests} tests failed out of {total_tests}!")

    return {
        "status": "success",
        "total": total_tests,
        "passed": passed_tests,
        "failed": failed_tests,
        "results": results
    }


def _ensure_test_accounts(comp):
    """Creates required test accounts on isolated test site if missing."""
    accounts = [
        {"account_name": "ضريبة مدخلات معلقة تحت المراجعة والاعتماد", "account_number": "1520", "parent_account": f"1500 - الأصول المتداولة الأخرى - {comp}", "account_type": "Tax", "root_type": "Asset"},
        {"account_name": "ضريبة القيمة المضافة للمدخلات 15%", "account_number": "1510", "parent_account": f"1500 - الأصول المتداولة الأخرى - {comp}", "account_type": "Tax", "root_type": "Asset"},
        {"account_name": "ضريبة القيمة المضافة للمخرجات 15%", "account_number": "2330", "parent_account": f"2300 - الخصوم المتداولة الأخرى - {comp}", "account_type": "Tax", "root_type": "Liability"},
        {"account_name": "ضريبة مدخلات غير قابلة للاسترداد", "account_number": "5235", "parent_account": f"5200 - المصاريف العمومية والإدارية - {comp}", "account_type": "Expense", "root_type": "Expense"},
        {"account_name": "مصروف الوقود والمحروقات", "account_number": "5120", "parent_account": f"5100 - تكاليف العمليات والمشاريع المباشرة - {comp}", "account_type": "Expense", "root_type": "Expense"},
        {"account_name": "مواد ومهمات تشغيل المشاريع", "account_number": "5150", "parent_account": f"5100 - تكاليف العمليات والمشاريع المباشرة - {comp}", "account_type": "Expense", "root_type": "Expense"},
        {"account_name": "نقد", "account_number": "1110", "parent_account": f"1100 - الأصول المتداولة - {comp}", "account_type": "Cash", "root_type": "Asset"},
        {"account_name": "عهد نقدية للمهندسين والمشرفين", "account_number": "1120", "parent_account": f"1100 - الأصول المتداولة - {comp}", "account_type": "Cash", "root_type": "Asset"}
    ]

    for acc in accounts:
        acc_full_name = f"{acc['account_number']} - {acc['account_name']} - {comp}"
        if not frappe.db.exists("Account", acc_full_name):
            try:
                # Find parent
                parent = acc["parent_account"]
                if not frappe.db.exists("Account", parent):
                    # Find root
                    roots = frappe.get_all("Account", filters={"company": comp, "root_type": acc["root_type"], "is_group": 1}, pluck="name", limit=1)
                    parent = roots[0] if roots else None

                doc = frappe.new_doc("Account")
                doc.company = comp
                doc.account_name = acc["account_name"]
                doc.account_number = acc["account_number"]
                doc.parent_account = parent
                doc.account_type = acc["account_type"]
                doc.is_group = 0
                doc.flags.ignore_permissions = True
                doc.insert()
            except Exception:
                pass
    frappe.db.commit()
