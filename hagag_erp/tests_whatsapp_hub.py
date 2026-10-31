# Copyright (c) 2026, Elsaidy ERP and contributors
# For license information, please see license.txt

from decimal import Decimal
import unittest
import frappe
from hagag_erp.whatsapp_bridge import (
	normalize_phone_number,
	parse_expense_from_text,
	receive_baileys_event
)
from hagag_erp.tax_engine import calculate_zatca_tax, create_draft_journal_entry


class TestElsaidyWhatsAppHub(unittest.TestCase):
	def setUp(self):
		frappe.set_user("Administrator")

	def test_phone_normalization_egypt_and_saudi(self):
		"""Verifies robust normalization of Egyptian, Saudi, and Arabic-numeral phone numbers."""
		# Egypt
		self.assertEqual(normalize_phone_number("01028632620"), "201028632620")
		self.assertEqual(normalize_phone_number("01145678901"), "201145678901")
		self.assertEqual(normalize_phone_number("01234567890"), "201234567890")
		self.assertEqual(normalize_phone_number("01555555555"), "201555555555")
		self.assertEqual(normalize_phone_number("+20 10 2863 2620"), "201028632620")
		self.assertEqual(normalize_phone_number("00201028632620"), "201028632620")

		# Saudi
		self.assertEqual(normalize_phone_number("0569589664"), "966569589664")
		self.assertEqual(normalize_phone_number("569589664"), "966569589664")
		self.assertEqual(normalize_phone_number("+966 56 958 9664"), "966569589664")
		self.assertEqual(normalize_phone_number("00966569589664"), "966569589664")

		# Arabic Numerals
		self.assertEqual(normalize_phone_number("٠١٠٢٨٦٣٢٦٢٠"), "201028632620")
		self.assertEqual(normalize_phone_number("٠٥٦٩٥٨٩٦٦٤"), "966569589664")

	def test_expense_text_parsing(self):
		"""Verifies natural language extraction of expense amounts, tax inclusiveness, and vendors."""
		# Inclusive VAT
		exp1 = parse_expense_from_text("صرفت 500 ريال بنزين للموقع شامل الضريبة")
		self.assertIsNotNone(exp1)
		self.assertEqual(exp1["amount"], Decimal("500"))
		self.assertTrue(exp1["is_inclusive"])

		# Exclusive VAT
		exp2 = parse_expense_from_text("شراء مواد بمبلغ 1000 ريال غير شامل الضريبة من مؤسسة الأفق")
		self.assertIsNotNone(exp2)
		self.assertEqual(exp2["amount"], Decimal("1000"))
		self.assertFalse(exp2["is_inclusive"])
		self.assertIn("مؤسسة الأفق", exp2["vendor"])

		# Arabic Numerals
		exp3 = parse_expense_from_text("فاتورة صيانة ١١٥٠ ريال شامل الضريبة")
		self.assertIsNotNone(exp3)
		self.assertEqual(exp3["amount"], Decimal("1150"))
		self.assertTrue(exp3["is_inclusive"])

		# Non-expense text
		exp4 = parse_expense_from_text("السلام عليكم ورحمة الله وبركاته، كيف الحال؟")
		self.assertIsNone(exp4)

	def test_zatca_tax_calculation_for_wa_expenses(self):
		"""Verifies exact 15% ZATCA calculation on WhatsApp parsed amounts."""
		calc_inc = calculate_zatca_tax(Decimal("1150.00"), is_inclusive=True)
		self.assertEqual(calc_inc["net_amount"], Decimal("1000.00"))
		self.assertEqual(calc_inc["tax_amount"], Decimal("150.00"))
		self.assertEqual(calc_inc["total_amount"], Decimal("1150.00"))

		calc_exc = calculate_zatca_tax(Decimal("1000.00"), is_inclusive=False)
		self.assertEqual(calc_exc["net_amount"], Decimal("1000.00"))
		self.assertEqual(calc_exc["tax_amount"], Decimal("150.00"))
		self.assertEqual(calc_exc["total_amount"], Decimal("1150.00"))

	def test_draft_journal_entry_creation_idempotency(self):
		"""Verifies that WhatsApp expense creation strictly creates a Draft (docstatus=0) and enforces idempotency."""
		company = frappe.db.get_single_value("Global Defaults", "default_company") or "شركة ركن سبل الأفق للمقاولات"
		expense_acc = frappe.db.get_value("Account", {"company": company, "root_type": "Expense", "is_group": 0}, "name")
		cash_acc = frappe.db.get_value("Account", {"company": company, "account_type": "Cash", "is_group": 0}, "name")

		test_op_id = f"WA-TEST-IDEMP-{frappe.generate_hash(length=8)}"

		# Line items
		lines = [
			{"account": expense_acc, "debit": 100.0, "credit": 0.0, "user_remark": "Test WA expense"},
			{"account": cash_acc, "debit": 0.0, "credit": 100.0, "user_remark": "Test WA cash"}
		]

		# 1st creation: must succeed as Draft
		jv1 = create_draft_journal_entry(company, lines, "Test WA idempotency", reference_id=test_op_id)
		self.assertEqual(jv1.docstatus, 0)
		self.assertTrue(jv1.name.startswith("ACC-JV-"))

		# 2nd creation with exact same reference_id: must return existing doc without creating duplicate
		jv2 = create_draft_journal_entry(company, lines, "Test WA idempotency duplicate", reference_id=test_op_id)
		self.assertEqual(jv1.name, jv2.name)

		# Clean up test JV
		frappe.db.delete("Journal Entry", {"name": jv1.name})
		frappe.db.delete("Journal Entry Account", {"parent": jv1.name})
		if frappe.db.table_exists("Custom Idempotency Log"):
			frappe.db.delete("Custom Idempotency Log", {"operation_id": test_op_id})
		frappe.db.commit()


def run_whatsapp_hub_tests():
	"""Runner helper to execute tests and print clear results."""
	suite = unittest.TestLoader().loadTestsFromTestCase(TestElsaidyWhatsAppHub)
	runner = unittest.TextTestRunner(verbosity=2)
	result = runner.run(suite)
	return {
		"total": result.testsRun,
		"failures": len(result.failures),
		"errors": len(result.errors),
		"was_successful": result.wasSuccessful()
	}
