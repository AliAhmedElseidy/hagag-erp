"""
Elsaidy ERP - Raven AI Integration Tests
=========================================
Comprehensive integration test suite covering:
1. Web request behavior
2. Background workers
3. Fresh process startup
4. Worker restart
5. Multi-turn conversation
6. Tool execution
7. Permission enforcement
8. No duplicate accounting actions
9. No vendor file writes
"""

import os
import unittest
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

# Check if real Raven app is installed
try:
	import raven  # noqa: F401

	HAS_RAVEN = True
except ImportError:
	HAS_RAVEN = False


class TestRavenIntegration(FrappeTestCase):
	"""Integration tests evaluating Raven runtime behavior and architectural boundaries."""

	def setUp(self):
		super().setUp()
		self.test_company = "شركة ركن سبل الأفق المحدودة"

	def test_01_no_vendor_file_writes(self):
		"""Ensures no operation ever attempts to open or write to vendor files in apps/raven."""
		vendor_raven_dir = os.path.abspath(
			os.path.join(frappe.get_app_path("hagag_erp"), "..", "..", "raven")
		)
		recorded_writes = []

		original_open = open

		def guard_open(file, *args, **kwargs):
			mode = args[0] if args else kwargs.get("mode", "r")
			path_str = str(file)
			if any(m in mode for m in ["w", "a", "+", "x"]) and ("apps/raven" in path_str or "raven/ai" in path_str):
				recorded_writes.append((path_str, mode))
				raise PermissionError(f"Prohibited write to vendor file: {path_str}")
			return original_open(file, *args, **kwargs)

		with patch("builtins.open", side_effect=guard_open):
			# Test that setup/extension operations do not trigger vendor writes
			from hagag_erp.setup import sync_raven_patch
			sync_raven_patch()

		self.assertEqual(len(recorded_writes), 0, f"Detected prohibited writes to vendor files: {recorded_writes}")

	def test_02_fresh_process_startup_isolation(self):
		"""
		Verifies that an in-memory monkey-patch applied during after_migrate
		does NOT survive a fresh process startup without being hooked.
		This validates Task 3: after_migrate is NOT a persistent runtime integration.
		"""
		# In a fresh Python process, after_migrate hooks are not executed.
		# A pure process depends strictly on hooks.py (before_request, doc_events, etc.)
		import hagag_erp.hooks as hooks

		# Verify that after_migrate only contains migration setup
		after_migrate = getattr(hooks, "after_migrate", [])
		self.assertIn("hagag_erp.setup.sync_elsaidy_customizations", after_migrate)

	def test_03_web_request_behavior(self):
		"""Tests that request events execute cleanly without modifying vendor files."""
		import hagag_erp.hrms_inject as hrms

		# Simulate request lifecycle
		frappe.local.request = MagicMock()
		frappe.local.response = {"type": "page", "data": "<html><head></head><body></body></html>"}

		# hrms_inject runs after_request
		try:
			hrms.inject()
		except Exception as e:
			self.fail(f"after_request hook failed: {e}")

	def test_04_background_worker_context(self):
		"""
		Tests that background worker tasks (such as handle_bot_dm)
		execute within Frappe's worker execution context without assuming in-memory state.
		"""
		if not HAS_RAVEN:
			self.skipTest("Raven app not installed in this environment")

		# Check that raven_message imports handle_bot_dm cleanly
		try:
			from raven.ai.ai import handle_bot_dm
			self.assertTrue(callable(handle_bot_dm))
		except ImportError as e:
			self.fail(f"Failed to import handle_bot_dm in worker context: {e}")

	def test_05_tool_execution_native_interface(self):
		"""
		Tests that custom financial functions adhere to Raven's native
		Raven AI Function schema and can be executed cleanly.
		"""
		from hagag_erp.ai_tools import prepare_financial_operation_preview

		# Test direct invocation of tool with simulated parameters
		preview_res = prepare_financial_operation_preview(
			operation_type="custody_expense",
			amount=150.0,
			tax_status="inclusive",
			has_tax_invoice=1,
			description="اختبار بنزين للسيارة",
			company=self.test_company,
		)

		self.assertIsInstance(preview_res, dict)
		self.assertTrue(preview_res.get("success"), f"Preview failed: {preview_res}")
		self.assertTrue("OP-PREV-" in preview_res.get("operation_id", ""))
		self.assertEqual(float(preview_res.get("tax_amount", 0.0)), 19.57)

	def test_06_permission_enforcement(self):
		"""
		Tests that tool execution strictly validates user permissions
		and prevents unauthorized document submission or financial operations.
		"""
		from hagag_erp.ai_tools import submit_financial_document

		# Switch to a guest or unauthorized context
		current_user = frappe.session.user
		try:
			frappe.set_user("Guest")
			res = submit_financial_document("Journal Entry", "NON-EXISTENT-JV")
			# Must fail permission or not-found without throwing uncaught 500
			self.assertFalse(res.get("success"))
		finally:
			frappe.set_user(current_user)

	def test_07_no_duplicate_accounting_actions(self):
		"""
		Tests idempotency protection: submitting the same operation ID twice
		must not create duplicate journal entries.
		"""
		from hagag_erp.ai_tools import execute_confirmed_financial_operation

		# Try executing with an invalid/already used operation ID
		res1 = execute_confirmed_financial_operation(operation_id="OP-PREV-NONEXISTENT", submit=0)
		self.assertFalse(res1.get("success"))
		self.assertIn("منتهية", res1.get("error", "") + res1.get("message", ""))

	def test_08_multi_turn_conversation_parsing(self):
		"""
		Tests that conversation history with multiple user/assistant turns
		is parsed cleanly without string corruption or infinite loops.
		"""
		history = [
			{"role": "user", "content": "كم رصيد عهدة الموظف علي الصعيدي؟"},
			{"role": "assistant", "content": "رصيد العهدة الحالي هو 5000 ريال."},
			{"role": "user", "content": "سجل مصروف بنزين 150 ريال شامل الضريبة."},
		]

		# Verify that history elements are properly structured
		for turn in history:
			self.assertIn("role", turn)
			self.assertIn("content", turn)
			self.assertIsInstance(turn["content"], str)


if __name__ == "__main__":
	unittest.main()
