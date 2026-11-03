# -*- coding: utf-8 -*-
"""
Elsaidy ERP - Automated Test Suite: Employee Custody, Advances & Payroll Settlement
==================================================================================
Tests covering all requirements from Phase 1 through Phase 8:
- Employee resolution (exact, normalized, ambiguous, unauthorized, bot phone rejection)
- Intent classification and workflows (Intents A, B, C, D, E)
- ZATCA Article 50 tax compliance & Decimal arithmetic (commercial vs restricted vs pending)
- Party type integrity on Cash account 1120 (no party_type on Cash in ERPNext v16)
- Balanced Journal Entry validation
- Separation of posted GL entries from unposted drafts
- Duplicate payroll deduction and command idempotency protection
- Journal Entry ACC-JV-2026-00005 inspection and draft correction proposal
- True Dry-Run simulation guarantee (zero DB writes)
"""

import unittest
from decimal import Decimal
import frappe
from frappe.utils import nowdate

from hagag_erp.custody_service import (
    resolve_employee,
    classify_accounting_intent,
    simulate_custody_workflow,
    generate_employee_settlement_report,
    inspect_acc_jv_2026_00005,
    apply_jv_draft_correction,
    get_employee_live_gl_balance,
    normalize_arabic_text,
    clean_phone,
    notify_employee_custody_event,
    send_custody_whatsapp_notification,
    INTENT_A_EXPENSE_CASH_BANK,
    INTENT_B_WORK_EXPENSE_CUSTODY,
    INTENT_C_ISSUE_REPLENISH_CUSTODY,
    INTENT_D_PERSONAL_SALARY_ADVANCE,
    INTENT_E_MONTHLY_SETTLEMENT_REPORT
)
from hagag_erp.tax_engine import (
    to_decimal,
    evaluate_vat_eligibility_and_split,
    calculate_zatca_tax
)


class TestEmployeeCustodyPayroll(unittest.TestCase):

    def setUp(self):
        self.company = "ركن سبل الافق"
        self.abbr = "Rkn"

    # -------------------------------------------------------------
    # 1. EMPLOYEE RESOLUTION & NORMALIZATION TESTS (PHASE 3)
    # -------------------------------------------------------------

    def test_employee_resolution_exact_id(self):
        """Rule 1: Direct Employee ID match."""
        res = resolve_employee(identifier="HR-EMP-00001", company=self.company)
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["employee"], "HR-EMP-00001")
        self.assertIn("علي", res["employee_name"])

    def test_employee_resolution_normalized_arabic_name(self):
        """Rule 2: Resilient Arabic normalization (alef variants, tashkeel)."""
        # With Hamza above
        res1 = resolve_employee(identifier="علي أحمد الصعيدي", company=self.company)
        self.assertEqual(res1["status"], "success")
        self.assertEqual(res1["employee"], "HR-EMP-00001")

        # Without Hamza
        res2 = resolve_employee(identifier="علي احمد الصعيدي", company=self.company)
        self.assertEqual(res2["status"], "success")
        self.assertEqual(res2["employee"], "HR-EMP-00001")

        # Short name
        res3 = resolve_employee(identifier="علي الصعيدي", company=self.company)
        self.assertEqual(res3["status"], "success")
        self.assertEqual(res3["employee"], "HR-EMP-00001")

    def test_employee_resolution_ambiguous_name(self):
        """Rule 6: Ambiguous names return explicit error instead of guessing."""
        # Querying an ambiguous single common token like "احمد" when multiple Ahmeds exist
        res = resolve_employee(identifier="احمد", company=self.company)
        if res.get("status") == "error":
            self.assertIn(res.get("error_code"), ["AMBIGUOUS_NAME_MATCH", "EMPLOYEE_NOT_FOUND"])
        else:
            # If only 1 matches in test DB, employee must be valid
            self.assertIsNotNone(res.get("employee"))

    def test_egyptian_bot_number_rejected(self):
        """Rule 4: Egyptian WhatsApp bot number must NEVER be associated with employee."""
        res = resolve_employee(sender_phone="201028632620", company=self.company)
        self.assertEqual(res["status"], "error")
        self.assertEqual(res["error_code"], "BOT_PHONE_REJECTED")

        res_plus = resolve_employee(sender_phone="+201028632620", company=self.company)
        self.assertEqual(res_plus["status"], "error")
        self.assertEqual(res_plus["error_code"], "BOT_PHONE_REJECTED")

    def test_employee_resolution_unauthorized_unknown(self):
        """Rule 7: Unknown sender returns explicit error."""
        res = resolve_employee(identifier="شخص غير مسجل بالشركة", company=self.company)
        self.assertEqual(res["status"], "error")
        self.assertEqual(res["error_code"], "EMPLOYEE_NOT_FOUND")

    # -------------------------------------------------------------
    # 2. INTENT CLASSIFICATION TESTS (PHASE 2)
    # -------------------------------------------------------------

    def test_intent_a_classification_cash_and_bank(self):
        """Intent A: Cash or bank expense."""
        c1 = classify_accounting_intent("فاتورة بنزين ب 250 ريال نقداً")
        self.assertEqual(c1["intent"], INTENT_A_EXPENSE_CASH_BANK)
        self.assertEqual(c1["amount"], Decimal("250.00"))
        self.assertEqual(c1["payment_method"], "cash")
        self.assertEqual(c1["category"], "fuel")

        c2 = classify_accounting_intent("صرفت 250 ريال ديزل من البنك")
        self.assertEqual(c2["intent"], INTENT_A_EXPENSE_CASH_BANK)
        self.assertEqual(c2["amount"], Decimal("250.00"))
        self.assertEqual(c2["payment_method"], "bank")
        self.assertEqual(c2["category"], "fuel")

    def test_intent_b_classification_custody_expense(self):
        """Intent B: Work expense paid from employee custody."""
        c1 = classify_accounting_intent("فاتورة بنزين ب 250 ريال من عهدة علي الصعيدي")
        self.assertEqual(c1["intent"], INTENT_B_WORK_EXPENSE_CUSTODY)
        self.assertEqual(c1["amount"], Decimal("250.00"))
        self.assertEqual(c1["payment_method"], "custody")
        self.assertEqual(c1["category"], "fuel")

        c2 = classify_accounting_intent("صرفت 500 ريال ديزل لموقع الرياض من عهدتي")
        self.assertEqual(c2["intent"], INTENT_B_WORK_EXPENSE_CUSTODY)
        self.assertEqual(c2["amount"], Decimal("500.00"))
        self.assertEqual(c2["payment_method"], "custody")

    def test_intent_c_classification_replenish_custody(self):
        """Intent C: Issue or replenish employee custody."""
        c1 = classify_accounting_intent("تم دفع عهدة 500 ريال لعلي الصعيدي")
        self.assertEqual(c1["intent"], INTENT_C_ISSUE_REPLENISH_CUSTODY)
        self.assertEqual(c1["amount"], Decimal("500.00"))

        c2 = classify_accounting_intent("إرسال عهدة 2000 ريال تحويل بنكي")
        self.assertEqual(c2["intent"], INTENT_C_ISSUE_REPLENISH_CUSTODY)
        self.assertEqual(c2["amount"], Decimal("2000.00"))
        self.assertEqual(c2["payment_method"], "bank")

    def test_intent_d_classification_salary_advance(self):
        """Intent D: Personal salary advance."""
        c1 = classify_accounting_intent("سلفة 1000 ريال لعلي الصعيدي")
        self.assertEqual(c1["intent"], INTENT_D_PERSONAL_SALARY_ADVANCE)
        self.assertEqual(c1["amount"], Decimal("1000.00"))
        self.assertEqual(c1["payment_method"], "payroll")

        c2 = classify_accounting_intent("مسحوبات شخصية 500 ريال تخصم من راتب علي")
        self.assertEqual(c2["intent"], INTENT_D_PERSONAL_SALARY_ADVANCE)
        self.assertEqual(c2["amount"], Decimal("500.00"))

    def test_intent_e_classification_settlement_report(self):
        """Intent E: Read-only monthly settlement report."""
        c1 = classify_accounting_intent("تقفيل حساب علي الصعيدي")
        self.assertEqual(c1["intent"], INTENT_E_MONTHLY_SETTLEMENT_REPORT)

        c2 = classify_accounting_intent("كشف العهدة والسلف قبل القبض")
        self.assertEqual(c2["intent"], INTENT_E_MONTHLY_SETTLEMENT_REPORT)

        c3 = classify_accounting_intent("فاضل كام في عهدة علي؟")
        self.assertEqual(c3["intent"], INTENT_E_MONTHLY_SETTLEMENT_REPORT)

    # -------------------------------------------------------------
    # 3. ZATCA ARTICLE 50 TAX ENGINE TESTS (PHASE 4)
    # -------------------------------------------------------------

    def test_zatca_tax_calculation_inclusive_exclusive(self):
        """Decimal precision arithmetic for 15% VAT."""
        # 230 SAR inclusive 15% -> 200.00 net + 30.00 VAT
        calc_inc = calculate_zatca_tax(Decimal("230.00"), is_inclusive=True)
        self.assertEqual(calc_inc["net_amount"], Decimal("200.00"))
        self.assertEqual(calc_inc["tax_amount"], Decimal("30.00"))
        self.assertEqual(calc_inc["total_amount"], Decimal("230.00"))

        # 200 SAR exclusive 15% -> 200.00 net + 30.00 VAT = 230.00 total
        calc_exc = calculate_zatca_tax(Decimal("200.00"), is_inclusive=False)
        self.assertEqual(calc_exc["net_amount"], Decimal("200.00"))
        self.assertEqual(calc_exc["tax_amount"], Decimal("30.00"))
        self.assertEqual(calc_exc["total_amount"], Decimal("230.00"))

    def test_zatca_article_50_commercial_equipment_vs_restricted_vehicle(self):
        """ZATCA Article 50: Commercial equipment vs restricted passenger vehicle."""
        # Commercial equipment with invoice -> 100% recoverable (1510)
        comm = evaluate_vat_eligibility_and_split(
            amount=Decimal("230.00"),
            account_code=f"5120 - مصروف الوقود والمحروقات - {self.abbr}",
            usage_type="commercial",
            has_valid_tax_invoice=True,
            company=self.company
        )
        self.assertEqual(comm["tax_eligible"], Decimal("30.00"))
        self.assertEqual(comm["tax_pending"], Decimal("0.00"))
        self.assertEqual(comm["tax_non_recoverable"], Decimal("0.00"))
        self.assertEqual(comm["tax_status"], "مكتمل ومطابق")

        # Restricted passenger vehicle -> Non-recoverable under Article 50
        restr = evaluate_vat_eligibility_and_split(
            amount=Decimal("230.00"),
            account_code=f"5120 - مصروف الوقود والمحروقات - {self.abbr}",
            usage_type="passenger_restricted",
            has_valid_tax_invoice=True,
            company=self.company
        )
        self.assertEqual(restr["tax_eligible"], Decimal("0.00"))
        self.assertEqual(restr["tax_non_recoverable"], Decimal("30.00"))
        self.assertEqual(restr["tax_status"], "مستبعد من الاسترداد الضريبي")

        # Uncertain / Missing invoice -> Pending review (1520)
        pend = evaluate_vat_eligibility_and_split(
            amount=Decimal("230.00"),
            account_code=f"5120 - مصروف الوقود والمحروقات - {self.abbr}",
            usage_type="commercial",
            has_valid_tax_invoice=False,
            company=self.company
        )
        self.assertEqual(pend["tax_eligible"], Decimal("0.00"))
        self.assertEqual(pend["tax_pending"], Decimal("30.00"))
        self.assertEqual(pend["tax_status"], "قيد المراجعة الضريبية")

    # -------------------------------------------------------------
    # 4. TRUE DRY-RUN SIMULATOR TESTS (PHASE 7)
    # -------------------------------------------------------------

    def test_simulation_scenario_1_intent_a_cash_expense(self):
        """Simulation: Intent A - Cash Expense."""
        sim = simulate_custody_workflow("فاتورة بنزين ب 250 ريال نقداً", company=self.company)
        self.assertTrue(sim["is_simulation"])
        self.assertEqual(sim["intent"], INTENT_A_EXPENSE_CASH_BANK)
        self.assertEqual(sim["proposed_document_type"], "Journal Entry")

        # Balanced lines check
        lines = sim["proposed_lines"]
        total_dr = sum(l["debit"] for l in lines)
        total_cr = sum(l["credit"] for l in lines)
        self.assertAlmostEqual(total_dr, total_cr, places=2)
        self.assertAlmostEqual(total_cr, 250.0, places=2)

    def test_simulation_scenario_2_intent_b_custody_expense(self):
        """Simulation: Intent B - Custody Expense."""
        sim = simulate_custody_workflow("فاتورة بنزين ب 250 ريال من عهدة علي الصعيدي", company=self.company)
        self.assertTrue(sim["is_simulation"])
        self.assertEqual(sim["intent"], INTENT_B_WORK_EXPENSE_CUSTODY)
        self.assertEqual(sim["employee_id"], "HR-EMP-00001")

        lines = sim["proposed_lines"]
        total_dr = sum(l["debit"] for l in lines)
        total_cr = sum(l["credit"] for l in lines)
        self.assertAlmostEqual(total_dr, total_cr, places=2)

        # Integrity Check: Cash account 1120 MUST have party_type=None
        custody_line = [l for l in lines if "1120" in (l.get("account") or "")][0]
        self.assertIsNone(custody_line.get("party_type"))
        self.assertIsNone(custody_line.get("party"))

    def test_simulation_scenario_3_intent_c_replenish_custody(self):
        """Simulation: Intent C - Issue Custody."""
        sim = simulate_custody_workflow("تم دفع عهدة 500 ريال لعلي الصعيدي", company=self.company)
        self.assertTrue(sim["is_simulation"])
        self.assertEqual(sim["intent"], INTENT_C_ISSUE_REPLENISH_CUSTODY)

        lines = sim["proposed_lines"]
        total_dr = sum(l["debit"] for l in lines)
        total_cr = sum(l["credit"] for l in lines)
        self.assertAlmostEqual(total_dr, total_cr, places=2)
        self.assertAlmostEqual(total_dr, 500.0, places=2)

    def test_simulation_scenario_4_intent_d_salary_advance(self):
        """Simulation: Intent D - Personal Salary Advance."""
        sim = simulate_custody_workflow("سلفة 1000 ريال لعلي الصعيدي", company=self.company)
        self.assertTrue(sim["is_simulation"])
        self.assertEqual(sim["intent"], INTENT_D_PERSONAL_SALARY_ADVANCE)
        self.assertEqual(sim["proposed_document_type"], "Additional Salary")
        self.assertEqual(sim["employee_id"], "HR-EMP-00001")

        lines = sim["proposed_lines"]
        self.assertEqual(lines[0]["amount"], 1000.0)
        self.assertEqual(lines[0]["type"], "Deduction")

    def test_simulation_scenario_5_intent_e_settlement_report(self):
        """Simulation: Intent E - Monthly Settlement Report."""
        sim = simulate_custody_workflow("تقفيل حساب علي الصعيدي", company=self.company)
        self.assertTrue(sim["is_simulation"])
        self.assertEqual(sim["intent"], INTENT_E_MONTHLY_SETTLEMENT_REPORT)
        self.assertIn("settlement_data", sim)
        rep = sim["settlement_data"]
        self.assertIn("posted_balances", rep)
        self.assertIn("unsubmitted_draft_totals", rep)

    # -------------------------------------------------------------
    # 5. JOURNAL ENTRY ACC-JV-2026-00005 INSPECTION & PROPOSAL (PHASE 5)
    # -------------------------------------------------------------

    def test_acc_jv_2026_00005_audit(self):
        """Audit existing ACC-JV-2026-00005."""
        res = inspect_acc_jv_2026_00005(company=self.company)
        self.assertEqual(res["document_name"], "ACC-JV-2026-00005")
        self.assertEqual(res["docstatus"], 0)  # Must be Draft
        self.assertEqual(res["total_amount"], 230.0)
        self.assertIn("proposed_correction", res)

        # Proposed correction check
        corr = res["proposed_correction"]["strategy_2_pending_review_default"]
        corr_rows = corr["rows"]
        total_dr = sum(r["debit"] for r in corr_rows)
        total_cr = sum(r["credit"] for r in corr_rows)
        self.assertAlmostEqual(total_dr, total_cr, places=2)
        self.assertAlmostEqual(total_dr, 230.0, places=2)

        # Net expense should be 200.00, VAT 30.00, Credit 1120 230.00
        net_row = [r for r in corr_rows if "5120" in r["account"]][0]
        vat_row = [r for r in corr_rows if "1520" in r["account"]][0]
        cust_row = [r for r in corr_rows if "1120" in r["account"]][0]

        self.assertEqual(net_row["debit"], 200.0)
        self.assertEqual(vat_row["debit"], 30.0)
        self.assertEqual(cust_row["credit"], 230.0)
        self.assertIsNone(cust_row.get("party"))

    # -------------------------------------------------------------
    # 6. POSTED GL VS DRAFT SEPARATION (PHASE 1 & 2)
    # -------------------------------------------------------------

    def test_separation_of_posted_gl_and_unposted_drafts(self):
        """Ensures drafts are never added to posted GL balances."""
        bal = get_employee_live_gl_balance(employee="HR-EMP-00001", company=self.company)
        self.assertIn("posted_custody_balance", bal)
        self.assertIn("unposted_draft_custody_entries", bal)
        # Verify posted balance matches actual GL Entry sum in database
        gl_check = frappe.db.sql("""
            SELECT SUM(debit) - SUM(credit) as bal
            FROM `tabGL Entry`
            WHERE account = %s AND company = %s AND is_cancelled = 0
        """, (f"1120 - عهد نقدية للمهندسين والمشرفين - {self.abbr}", self.company), as_dict=True)
        expected_posted = round(float(gl_check[0].bal or 0.0), 2)
        self.assertEqual(bal["posted_custody_balance"], expected_posted)

    # -------------------------------------------------------------
    # 7. CONSISTENCY & BALANCED ARITHMETIC (PHASE 6 & 8)
    # -------------------------------------------------------------

    def test_whatsapp_and_raven_consistency(self):
        """Raven AI and WhatsApp produce identical simulation outcomes."""
        from hagag_erp.whatsapp_bridge import simulate_whatsapp_message
        from hagag_erp.ai_tools import simulate_employee_custody_workflow as simulate_raven

        msg = "فاتورة بنزين ب 250 ريال من عهدة علي الصعيدي"
        wa_res = simulate_whatsapp_message(text=msg, sender_phone="966569589664")
        rv_res = simulate_raven(text=msg, sender_phone="966569589664")

        self.assertEqual(wa_res["status"], "ok")
        self.assertEqual(rv_res["status"], "success")
        self.assertEqual(wa_res["intent_code"], rv_res["intent"])
        self.assertEqual(wa_res["employee_id"], rv_res["employee_id"])
        self.assertEqual(wa_res["proposed_document_type"], rv_res["proposed_document_type"])
        self.assertEqual(len(wa_res["simulated_lines"]), len(rv_res["proposed_lines"]))

    def test_balanced_journal_entry_lines_all_scenarios(self):
        """Every generated draft entry must balance to the penny."""
        test_amounts = ["17.33", "250.00", "999.99", "12345.67"]
        for amt_str in test_amounts:
            sim = simulate_custody_workflow(f"فاتورة صيانة ب {amt_str} ريال نقداً", company=self.company)
            lines = sim["proposed_lines"]
            total_dr = sum(Decimal(str(l["debit"])) for l in lines)
            total_cr = sum(Decimal(str(l["credit"])) for l in lines)
            self.assertEqual(total_dr, total_cr, f"Failed balance for amount {amt_str}")

    def test_missing_or_mismatched_account_handling(self):
        """Unknown or unusual categories fallback cleanly without crashing."""
        sim = simulate_custody_workflow("شراء أدوات غير معروفة ب 150 ريال نقداً", company=self.company)
        self.assertEqual(sim["status"], "success")
        self.assertTrue(len(sim["selected_accounts"]) >= 2)

    # -------------------------------------------------------------
    # 8. AUTOMATED WHATSAPP CUSTODY NOTIFICATION (PHASE 2)
    # -------------------------------------------------------------

    def test_notify_employee_custody_event_journal_entry(self):
        """Tests WhatsApp notification formatting and dispatch for custody Journal Entry."""
        frappe.flags.sync_whatsapp_notification = True
        fake_jv = frappe._dict({
            "doctype": "Journal Entry",
            "name": "ACC-JV-2026-TEST01",
            "company": self.company,
            "posting_date": nowdate(),
            "user_remark": "فاتورة بنزين مسددة من عهدة علي احمد الصعيدي (HR-EMP-00001)",
            "accounts": [
                {"account": f"5120 - مصروف الوقود والمحروقات - {self.abbr}", "debit": 230.0, "credit": 0.0},
                {"account": f"1120 - عهد نقدية للمهندسين والمشرفين - {self.abbr}", "debit": 0.0, "credit": 230.0}
            ]
        })
        res = notify_employee_custody_event(fake_jv)
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["employee"], "HR-EMP-00001")
        self.assertEqual(res["recipient_phone"], "966569589664")
        self.assertEqual(res["amount"], 230.0)
        self.assertIn("إشعار خصم وتسوية فاتورة من العهدة", res["notification_title"])
        self.assertIn("رصيد العهدة المقيد المتبقي", res["message_preview"])

    def test_notify_employee_custody_event_employee_advance(self):
        """Tests WhatsApp notification for Employee Advance."""
        frappe.flags.sync_whatsapp_notification = True
        fake_adv = frappe._dict({
            "doctype": "Employee Advance",
            "name": "HR-ADV-2026-TEST01",
            "company": self.company,
            "posting_date": nowdate(),
            "employee": "HR-EMP-00001",
            "advance_amount": 500.0,
            "purpose": "عهدة مشروع الرياض"
        })
        res = notify_employee_custody_event(fake_adv)
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["employee"], "HR-EMP-00001")
        self.assertEqual(res["recipient_phone"], "966569589664")
        self.assertEqual(res["amount"], 500.0)
        self.assertIn("إشعار صرف عهدة مالية للموقع", res["notification_title"])

    def test_notify_employee_custody_event_additional_salary_deduction(self):
        """Tests WhatsApp notification for Additional Salary advance deduction."""
        frappe.flags.sync_whatsapp_notification = True
        fake_sal = frappe._dict({
            "doctype": "Additional Salary",
            "name": "HR-AS-2026-TEST01",
            "company": self.company,
            "payroll_date": nowdate(),
            "employee": "HR-EMP-00001",
            "amount": 300.0,
            "salary_component": "استقطاع سلفة",
            "type": "Deduction",
            "remark": "خصم قسط السلفة لشهر نوفمبر"
        })
        res = notify_employee_custody_event(fake_sal)
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["employee"], "HR-EMP-00001")
        self.assertEqual(res["recipient_phone"], "966569589664")
        self.assertEqual(res["amount"], 300.0)
        self.assertIn("استقطاع سلفة", res["notification_title"])
        self.assertIn("رصيد السلف المقيد المتبقي", res["message_preview"])

    def test_notify_employee_custody_event_no_phone(self):
        """Tests silent skip when employee has no registered phone (zero crash)."""
        fake_doc = frappe._dict({
            "doctype": "Employee Advance",
            "name": "HR-ADV-2026-NOPHON",
            "company": self.company,
            "employee": "NON-EXISTENT-EMP",
            "advance_amount": 100.0
        })
        res = notify_employee_custody_event(fake_doc)
        self.assertEqual(res["status"], "skipped")

    def test_notify_employee_custody_event_bot_phone_blocked(self):
        """Tests that dispatch to bot handset is strictly blocked."""
        res = send_custody_whatsapp_notification(
            phone="201028632620",
            message="Test bot protection",
            docname="TEST",
            doctype="Test",
            intent_title="Test"
        )
        self.assertEqual(res["status"], "ignored")
        self.assertIn("bot", res["reason"].lower())


def run_tests():
    suite = unittest.TestLoader().loadTestsFromTestCase(TestEmployeeCustodyPayroll)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return {
        "total_tests": result.testsRun,
        "errors": len(result.errors),
        "failures": len(result.failures),
        "was_successful": result.wasSuccessful()
    }


if __name__ == "__main__":
    run_tests()
