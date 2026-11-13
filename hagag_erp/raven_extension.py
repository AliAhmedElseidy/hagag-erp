"""
Elsaidy ERP - Raven AI Safe Extension Module
=============================================
Provides safe, non-destructive runtime extension of Raven AI functionality
without modifying or overwriting any Raven Core vendor files on disk.

Architectural Policy:
Zero modifications to vendor core files in /home/frappe/frappe-bench/apps/raven/.
"""

import importlib.util
import os

import frappe


def load_raven_extension_module():
	"""
	Loads the customized Raven agent implementation into memory with
	package context bound to 'raven.ai' to resolve internal references safely.
	"""
	patch_path = os.path.join(os.path.dirname(__file__), "raven_patch.py")
	if not os.path.exists(patch_path):
		return None

	spec = importlib.util.spec_from_file_location("raven.ai._elsaidy_agents_integration", patch_path)
	if not spec or not spec.loader:
		return None

	custom_mod = importlib.util.module_from_spec(spec)
	custom_mod.__package__ = "raven.ai"
	spec.loader.exec_module(custom_mod)
	return custom_mod


def apply_raven_extension():
	"""
	Dynamically hooks Elsaidy's multi-turn & Arabic accounting enhancements
	into Raven AI's request handlers at runtime in memory.

	Returns True if successfully patched, False otherwise.
	"""
	try:
		import raven.ai.agents_integration as rai
		import raven.ai.ai as rai_ai

		custom_mod = load_raven_extension_module()
		if not custom_mod:
			return False

		# In-memory hook injection (non-destructive)
		rai.handle_ai_request_sync = custom_mod.handle_ai_request_sync
		rai.handle_ai_request_async = custom_mod.handle_ai_request_async
		rai.RavenAgentManager = custom_mod.RavenAgentManager
		rai_ai.handle_ai_request_sync = custom_mod.handle_ai_request_sync

		return True
	except ImportError:
		# Raven app not active/installed in the current environment
		return False
	except Exception as e:
		frappe.log_error(f"Failed to apply Raven runtime extension: {e}", "Raven Extension")
		return False
