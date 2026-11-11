"""
Hagag ERP - ZATCA Pure Calculation & Tax Engine Unit Tests
==========================================================
Isolated unit tests covering pure business logic with ZERO database mutations:
- All DB calls (frappe.db) are strictly mocked.
- Tests execute purely in-memory using Python Decimal arithmetic.
- Any test failure raises RuntimeError to force CI failure (non-zero exit code).

Test Coverage:
1. Saudi Contracting IPC tax base, retention, and advance recovery reconciliation.
2. Private vs Government (Etimad) time-of-supply rules.
3. Article 50 input tax recovery eligibility & split (Commercial Fuel vs Restricted Vehicle).
4. Mandatory ZATCA tax account mapping (1510, 1520, 2330, 5235) with mocked DB.
5. Document submission gating on unapproved tax reviews (in-memory mock doc).
6. Decimal ROUND_HALF_UP precision.
"""

import os
import sys
from decimal import Decimal
from unittest.mock import MagicMock, patch

# Ensure parent and current directory are on sys.path for standalone or bench execution
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
for p in [parent_dir, current_dir]:
	if p not in sys.path:
		sys.path.insert(0, p)

try:
	import frappe
except ImportError:

	class MockFrappeValidationError(Exception):
		pass

	mock_frappe = MagicMock()
	mock_frappe.ValidationError = MockFrappeValidationError
	mock_frappe._ = lambda msg: msg

	def _mock_throw(msg, title=None):
		raise MockFrappeValidationError(msg)

	mock_frappe.throw = _mock_throw
	sys.modules["frappe"] = mock_frappe
	sys.modules["frappe.utils"] = mock_frappe.utils
	import frappe

try:
	from hagag_erp.tax_engine import (
		calculate_contracting_ipc_tax_base,
		calculate_ipc_tax_breakdown,
		calculate_zatca_tax,
		evaluate_vat_eligibility_and_split,
		get_company_tax_accounts,
		round_currency,
		to_decimal,
		validate_input_vat_deductibility,
		validate_tax_review_before_submit,
	)
except ImportError:
	from tax_engine import (
		calculate_contracting_ipc_tax_base,
		calculate_ipc_tax_breakdown,
		calculate_zatca_tax,
		evaluate_vat_eligibility_and_split,
		get_company_tax_accounts,
		round_currency,
		to_decimal,
		validate_input_vat_deductibility,
		validate_tax_review_before_submit,
	)


class StrictFrappeDBMock:
	"""Strict mock that enforces expected company and chart accounts without loose MagicMock."""

	def exists(self, doctype, name):
		if doctype == "Company" and name == "ركن سبل الافق":
			return True
		if doctype == "Account" and any(k in str(name) for k in ["1510", "1520", "2330", "5235"]):
			return True
		return False

	def get_value(self, doctype, filters, fieldname="name"):
		if doctype == "Company":
			if (isinstance(filters, str) and filters == "ركن سبل الافق") or (
				isinstance(filters, dict) and filters.get("name") == "ركن سبل الافق"
			):
				if fieldname == "abbr":
					return "Rkn"
				return "ركن سبل الافق"
		return None


def test_contracting_ipc_tax_breakdown():
	"""Verify contracting IPC tax base calculation matches ZATCA requirements."""
	res = calculate_ipc_tax_breakdown(
		work_completed_amount=50000.0,
		advance_recovery_amount=5000.0,
		retention_pct=Decimal("10.00"),
		contract_type="عقد تجاري خاص",
	)
	assert res["taxable_base"] == Decimal("45000.00"), f"Expected 45000, got {res['taxable_base']}"
	assert res["vat_amount"] == Decimal("6750.00"), f"Expected 6750, got {res['vat_amount']}"
	assert res["retention_amount"] == Decimal("5000.00"), f"Expected 5000, got {res['retention_amount']}"
	assert res["net_payable"] == Decimal("46750.00"), f"Expected 46750, got {res['net_payable']}"
	assert res["time_of_supply_rule"] == "certification_date", (
		f"Expected certification_date, got {res['time_of_supply_rule']}"
	)

	# Also test through the convenience alias
	res_alias = calculate_contracting_ipc_tax_base(
		work_done_amount=50000.0,
		advance_recovery_amount=5000.0,
		retention_pct=Decimal("10.00"),
		contract_type="عقد تجاري خاص",
	)
	assert res_alias["taxable_base"] == Decimal("45000.00")
	return True


def test_government_contract_time_of_supply():
	"""Verify government contract time-of-supply rule (Etimad platform)."""
	res = calculate_ipc_tax_breakdown(
		work_completed_amount=100000.0,
		advance_recovery_amount=0.0,
		retention_pct=Decimal("5.00"),
		contract_type="عقد حكومي منصة اعتماد",
	)
	assert res["time_of_supply_rule"] == "payment_date", (
		f"Expected payment_date, got {res['time_of_supply_rule']}"
	)
	assert res["vat_amount"] == Decimal("15000.00")
	return True


def test_company_tax_accounts():
	"""Ensure standard Saudi 15% VAT accounts are correctly mapped using StrictFrappeDBMock."""
	mock_db = StrictFrappeDBMock()
	with patch("frappe.db", mock_db):
		accs = get_company_tax_accounts("ركن سبل الافق")
		assert "2330" in accs["output_vat"], f"Invalid output_vat: {accs['output_vat']}"
		assert "1510" in accs["recoverable_vat"], f"Invalid recoverable_vat: {accs['recoverable_vat']}"
		assert "1520" in accs["pending_vat"], f"Invalid pending_vat: {accs['pending_vat']}"
		assert "5235" in accs["non_recoverable_vat"], (
			f"Invalid non_recoverable_vat: {accs['non_recoverable_vat']}"
		)
	return True


def test_rounding_precision():
	"""Verify Decimal half-up 0.01 precision."""
	val1 = round_currency(Decimal("10.005"))
	assert val1 == Decimal("10.01"), f"Expected 10.01, got {val1}"
	val2 = round_currency(Decimal("10.004"))
	assert val2 == Decimal("10.00"), f"Expected 10.00, got {val2}"
	return True


def test_zatca_tax_calculation():
	"""Verify base tax calculation and gross total computation."""
	tax = calculate_zatca_tax(Decimal("1000.00"), is_inclusive=False, vat_rate_pct=Decimal("15.00"))
	assert tax["net_amount"] == Decimal("1000.00"), f"Expected 1000, got {tax['net_amount']}"
	assert tax["tax_amount"] == Decimal("150.00"), f"Expected 150, got {tax['tax_amount']}"
	assert tax["total_amount"] == Decimal("1150.00"), f"Expected 1150, got {tax['total_amount']}"
	return True


def test_article_50_vat_eligibility_commercial_fuel():
	"""Verify Article 50: commercial equipment fuel is approved and 100% deductible."""
	mock_db = StrictFrappeDBMock()
	with patch("frappe.db", mock_db):
		res = evaluate_vat_eligibility_and_split(
			amount=115.0,
			expense_account="5210 - وقود ومحروقات شاحنات ومعدات ثقيلة - Rkn",
			usage_type="commercial",
			has_valid_tax_invoice=True,
			company="ركن سبل الافق",
		)
		assert res["eligibility_status"] == "approved_recoverable", (
			f"Expected approved_recoverable, got {res['eligibility_status']}"
		)
		assert res["tax_eligible"] == Decimal("15.00"), f"Expected 15.00, got {res['tax_eligible']}"
		assert res["tax_pending"] == Decimal("0.00")
		assert res["tax_non_recoverable"] == Decimal("0.00")
	return True


def test_article_50_vat_eligibility_restricted_vehicle():
	"""Verify Article 50: restricted private vehicle is non-recoverable."""
	mock_db = StrictFrappeDBMock()
	with patch("frappe.db", mock_db):
		res = evaluate_vat_eligibility_and_split(
			amount=115.0,
			expense_account="5210 - وقود سيارات خاصة ومقيدة - Rkn",
			usage_type="restricted_vehicle",
			has_valid_tax_invoice=True,
			non_recoverable_policy="designated_expense_account",
			company="ركن سبل الافق",
		)
		assert res["eligibility_status"] == "non_recoverable", (
			f"Expected non_recoverable, got {res['eligibility_status']}"
		)
		assert res["tax_eligible"] == Decimal("0.00")
		assert res["tax_non_recoverable"] == Decimal("15.00"), (
			f"Expected 15.00, got {res['tax_non_recoverable']}"
		)
	return True


def test_tax_review_before_submit_hook():
	"""Verify submission blocking on unapproved tax review status using in-memory mock."""

	class MockDoc:
		def __init__(self, name, status, doctype="Journal Entry"):
			self.name = name
			self.custom_tax_review_status = status
			self.doctype = doctype
			self.accounts = []
			self.taxes = []

	blocked = False
	doc = MockDoc("TEST-JV-001", "pending_review")
	try:
		validate_tax_review_before_submit(doc)
	except frappe.ValidationError:
		blocked = True
	assert blocked is True, "Expected submission to be blocked for pending_review status"

	# Also test via alias
	blocked_alias = False
	try:
		validate_input_vat_deductibility(doc)
	except frappe.ValidationError:
		blocked_alias = True
	assert blocked_alias is True, "Expected submission to be blocked via alias"
	return True


def run_all_tests():
	"""Executes all pure unit tests and returns summary dictionary.

	CRITICAL CI SAFETY:
	If any test fails, raises RuntimeError immediately so that `bench execute`,
	pytest, or GitHub Actions CI processes exit with a non-zero failure code.
	"""
	tests = [
		("Contracting IPC Breakdown & Reconciliation", test_contracting_ipc_tax_breakdown),
		("Government Etimad Time of Supply", test_government_contract_time_of_supply),
		("Company Tax Accounts Mapping (Mocked DB)", test_company_tax_accounts),
		("Decimal Half-Up Precision", test_rounding_precision),
		("Standard 15% ZATCA Tax Calculation", test_zatca_tax_calculation),
		("Article 50 Commercial Fuel Deduction", test_article_50_vat_eligibility_commercial_fuel),
		("Article 50 Restricted Vehicle Exclusion", test_article_50_vat_eligibility_restricted_vehicle),
		("Tax Review Submission Gating Hook", test_tax_review_before_submit_hook),
	]

	passed = 0
	failed = 0
	results = []

	print("\n" + "=" * 70)
	print("RUNNING HAGAG ERP ZATCA PURE UNIT TEST SUITE (ZERO DB MUTATIONS)")
	print("=" * 70)

	for name, fn in tests:
		try:
			fn()
			print(f"  ✔ [PASS] {name}")
			passed += 1
			results.append({"name": name, "status": "PASS", "error": None})
		except Exception as e:
			print(f"  ✖ [FAIL] {name}: {e}")
			failed += 1
			results.append({"name": name, "status": "FAIL", "error": str(e)})

	print("=" * 70)
	print(f"TOTAL: {len(tests)} | PASSED: {passed} | FAILED: {failed}")
	print("=" * 70 + "\n")

	if failed > 0:
		failed_names = [r["name"] for r in results if r["status"] == "FAIL"]
		raise RuntimeError(
			f"ZATCA pure test suite FAILED: {failed} out of {len(tests)} tests failed: {', '.join(failed_names)}"
		)

	return {"total": len(tests), "passed": passed, "failed": failed, "results": results}


if __name__ == "__main__":
	import sys

	try:
		summary = run_all_tests()
		sys.exit(0)
	except Exception as exc:
		print(f"\nFATAL TEST SUITE FAILURE: {exc}", file=sys.stderr)
		sys.exit(1)
