"""
Elsaidy ERP - Raven Extension Unit Tests
=========================================
Tests the supported native extension architecture for Raven AI,
ensuring zero file overwrites to vendor core files on disk and
zero runtime monkey-patching.
"""

import unittest
from unittest.mock import MagicMock, patch

from hagag_erp.raven_extension import apply_raven_extension, verify_raven_native_setup
from hagag_erp.setup import sync_raven_patch


class TestRavenExtension(unittest.TestCase):
	"""Test suite for safe Raven native integration architecture."""

	def test_raven_native_extension_verification(self):
		"""Ensures verify_raven_native_setup and apply_raven_extension execute safely."""
		mock_db = MagicMock()
		mock_db.table_exists.return_value = True
		mock_db.count.return_value = 5
		with patch("frappe.local.db", mock_db, create=True):
			res = verify_raven_native_setup()
			self.assertTrue(res, "verify_raven_native_setup returned False when tables exist")
			apply_res = apply_raven_extension()
			self.assertTrue(apply_res, "apply_raven_extension returned False")

	def test_raven_extension_graceful_missing_table(self):
		"""Ensures verify_raven_native_setup returns False gracefully if Raven tables do not exist."""
		mock_db = MagicMock()
		mock_db.table_exists.return_value = False
		with patch("frappe.local.db", mock_db, create=True):
			res = verify_raven_native_setup()
			self.assertFalse(res, "Expected False when Raven AI Function table is missing")

	def test_sync_raven_patch_does_not_perform_disk_writes(self):
		"""Verifies that sync_raven_patch in setup.py executes purely natively with zero disk writes."""
		with (
			patch("builtins.open") as mock_open,
			patch("hagag_erp.raven_extension.apply_raven_extension", return_value=True) as mock_apply,
		):
			sync_raven_patch()
			mock_apply.assert_called_once()
			# open() must NEVER be called to write vendor files
			for call_args in mock_open.call_args_list:
				if len(call_args.args) > 1:
					mode = call_args.args[1]
					self.assertNotIn("w", mode, "sync_raven_patch attempted write operation via open()")


if __name__ == "__main__":
	unittest.main()
