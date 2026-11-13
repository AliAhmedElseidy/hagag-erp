"""
Elsaidy ERP - Raven AI Native Extension Module
===============================================
Provides supported native configuration of Raven AI functionality
without modifying or overwriting any Raven Core vendor files on disk,
and without runtime monkey-patching.

Supported Integration Mechanisms:
1. Native DocType: 'Raven AI Function' (type="Custom Function", function_path="hagag_erp.ai_tools.<fn>")
2. Child Table: 'Raven Bot Function' in 'Raven Bot' (dynamic loading via create_raven_tools)
3. Bot Prompts: 'Raven Bot.instruction' with dynamic_instructions=1 (RTL formatting, anti-hallucination)
"""

import os

import frappe


def verify_raven_native_setup():
	"""
	Verifies that Raven AI native extension points (DocType 'Raven AI Function'
	and child table 'bot_functions' on 'Raven Bot') are properly configured
	in Frappe database without modifying vendor core files or monkey-patching.
	"""
	try:
		if not frappe.db.table_exists("Raven AI Function"):
			return False
		custom_fn_count = frappe.db.count("Raven AI Function", {"type": "Custom Function"})
		return custom_fn_count > 0
	except Exception:
		return False


def load_raven_extension_module():
	"""
	Legacy helper retained for compatibility. Returns None as monkey-patching is eliminated.
	"""
	return None


def apply_raven_extension():
	"""
	Supported native Raven extension interface.
	Zero monkey-patching, zero vendor disk modifications.
	Custom tools are registered natively in Raven AI Function and loaded
	by Raven's agents SDK via create_raven_tools().
	"""
	return verify_raven_native_setup()
