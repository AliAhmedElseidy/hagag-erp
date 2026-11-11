"""
Elsaidy ERP - Raven Extension Unit Tests
=========================================
Tests the non-destructive in-memory runtime extension for Raven AI,
ensuring zero file overwrites to vendor core files on disk.
"""

import sys
import unittest
from unittest.mock import MagicMock, patch

from hagag_erp.raven_extension import apply_raven_extension, load_raven_extension_module
from hagag_erp.setup import sync_raven_patch


class TestRavenExtension(unittest.TestCase):
	"""Test suite for safe Raven extension architecture."""

	def test_raven_extension_module_loads_successfully(self):
		"""Ensures raven_patch.py can be loaded into memory without errors."""
		mod = load_raven_extension_module()
		self.assertIsNotNone(mod, "load_raven_extension_module returned None")
		self.assertTrue(hasattr(mod, "RavenAgentManager"), "RavenAgentManager missing from extension")
		self.assertTrue(hasattr(mod, "handle_ai_request_sync"), "handle_ai_request_sync missing")
		self.assertTrue(hasattr(mod, "handle_ai_request_async"), "handle_ai_request_async missing")

	def test_apply_raven_extension_in_memory_injection(self):
		"""Ensures apply_raven_extension dynamically injects into raven modules without disk write."""
		mock_rai = MagicMock()
		mock_rai_ai = MagicMock()

		with patch.dict(
			sys.modules,
			{
				"raven": MagicMock(),
				"raven.ai": MagicMock(),
				"raven.ai.agents_integration": mock_rai,
				"raven.ai.ai": mock_rai_ai,
			},
		):
			success = apply_raven_extension()
			self.assertTrue(success, "apply_raven_extension failed during mock injection")
			self.assertTrue(callable(mock_rai.handle_ai_request_sync))
			self.assertTrue(callable(mock_rai_ai.handle_ai_request_sync))
			self.assertIsNotNone(mock_rai.RavenAgentManager)

	def test_raven_extension_graceful_missing_app(self):
		"""Ensures apply_raven_extension returns False gracefully if Raven is not installed."""
		with patch.dict(sys.modules):
			if "raven.ai.agents_integration" in sys.modules:
				del sys.modules["raven.ai.agents_integration"]
			with patch("builtins.__import__", side_effect=ImportError("No module named 'raven'")):
				res = apply_raven_extension()
				self.assertFalse(res, "Expected False when raven import fails")

	def test_sync_raven_patch_does_not_perform_disk_writes(self):
		"""Verifies that sync_raven_patch in setup.py executes purely in memory with zero disk writes."""
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
