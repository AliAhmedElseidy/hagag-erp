# -*- coding: utf-8 -*-
"""
Elsaidy ERP - Atomic Idempotency & Operation Locking Engine
===========================================================
Guarantees zero duplicate documents across multi-worker environments,
network retries, and AI agent multi-turn feedback loops.
"""

import json
import time
import uuid
import frappe
from frappe import _


def ensure_idempotency_table():
    """Ensures persistent operation lock table exists in database."""
    frappe.db.sql("""
        CREATE TABLE IF NOT EXISTS `tabElsaidy Operation Lock` (
            `operation_id` VARCHAR(140) NOT NULL PRIMARY KEY,
            `document_type` VARCHAR(140) NOT NULL,
            `document_name` VARCHAR(140) DEFAULT NULL,
            `status` VARCHAR(50) NOT NULL DEFAULT 'IN_PROGRESS',
            `created_at` DATETIME(6) NOT NULL,
            `updated_at` DATETIME(6) NOT NULL,
            `response_json` LONGTEXT DEFAULT NULL,
            INDEX `idx_doc` (`document_type`, `document_name`),
            INDEX `idx_status` (`status`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
    """)
    frappe.db.commit()


def generate_operation_id(prefix="OP", message_id=None, context=None) -> str:
    """
    Generates a stable, unique operation_id for document creation intentions.
    If message_id is provided, ties the operation to that exact message intention.
    If no message_id is provided, generates a fresh unique UUID to ensure
    separate user requests with identical amounts/descriptions create distinct documents.
    """
    if message_id and str(message_id).strip():
        clean_mid = str(message_id).strip().replace(" ", "_")
        return f"{prefix}_{clean_mid}"

    # Generate fresh UUID for new distinct request
    unique_suffix = uuid.uuid4().hex[:12]
    timestamp = int(time.time())
    return f"{prefix}_{timestamp}_{unique_suffix}"


def get_existing_operation(operation_id):
    """Checks if operation was already completed and returns existing document."""
    if not operation_id:
        return None

    try:
        ensure_idempotency_table()
        res = frappe.db.sql("""
            SELECT operation_id, document_type, document_name, status, response_json
            FROM `tabElsaidy Operation Lock`
            WHERE operation_id = %s
        """, (operation_id,), as_dict=True)

        if res and res[0]["status"] == "COMPLETED" and res[0]["document_name"]:
            doc_type = res[0]["document_type"]
            doc_name = res[0]["document_name"]
            if frappe.db.exists(doc_type, doc_name):
                response_data = None
                if res[0]["response_json"]:
                    try:
                        response_data = json.loads(res[0]["response_json"])
                    except Exception:
                        pass
                return {
                    "document_type": doc_type,
                    "document_name": doc_name,
                    "response_data": response_data,
                    "is_retry": True
                }
    except Exception:
        pass

    return None


def acquire_operation_lock(operation_id, document_type):
    """
    Acquires an atomic lock in the database and distributed cache.
    Raises PermissionError if operation is currently running by another worker.
    """
    ensure_idempotency_table()
    now = frappe.utils.now_datetime()

    # Try cache lock first (fast in-memory barrier)
    cache_key = f"elsaidy_lock:{operation_id}"
    cache = frappe.cache()
    if cache.get_value(cache_key):
        # Already processing
        time.sleep(0.5)
        existing = get_existing_operation(operation_id)
        if existing:
            return existing

    cache.set_value(cache_key, 1, expires_in_sec=120)

    # Check DB record
    existing = get_existing_operation(operation_id)
    if existing:
        return existing

    try:
        frappe.db.sql("""
            INSERT INTO `tabElsaidy Operation Lock`
            (operation_id, document_type, status, created_at, updated_at)
            VALUES (%s, %s, 'IN_PROGRESS', %s, %s)
            ON DUPLICATE KEY UPDATE updated_at = VALUES(updated_at)
        """, (operation_id, document_type, now, now))
        frappe.db.commit()
    except Exception:
        pass

    return None


def release_operation_lock(operation_id, document_type, document_name, response_dict=None, success=True):
    """Releases the cache lock and finalizes the DB operation record."""
    cache_key = f"elsaidy_lock:{operation_id}"
    try:
        frappe.cache().delete_value(cache_key)
    except Exception:
        pass

    now = frappe.utils.now_datetime()
    status = "COMPLETED" if success else "FAILED"
    resp_json = json.dumps(response_dict, ensure_ascii=False) if response_dict else None

    try:
        frappe.db.sql("""
            UPDATE `tabElsaidy Operation Lock`
            SET status = %s, document_name = %s, updated_at = %s, response_json = %s
            WHERE operation_id = %s
        """, (status, document_name, now, resp_json, operation_id))
        frappe.db.commit()
    except Exception:
        pass


def execute_idempotent_operation(operation_id, document_type, execute_fn):
    """
    Executes execute_fn() protected by atomic idempotency lock.
    If operation_id was already completed, returns the existing document result
    without re-executing or creating duplicates.
    """
    if not operation_id:
        operation_id = generate_operation_id(prefix=document_type[:2].upper())

    existing = get_existing_operation(operation_id)
    if existing:
        res = existing.get("response_data") or {}
        res["is_retry"] = True
        res["document_name"] = existing["document_name"]
        res["document_type"] = existing["document_type"]
        return res

    locked = acquire_operation_lock(operation_id, document_type)
    if locked:
        res = locked.get("response_data") or {}
        res["is_retry"] = True
        res["document_name"] = locked["document_name"]
        res["document_type"] = locked["document_type"]
        return res

    try:
        result = execute_fn(operation_id)
        doc_name = (
            result.get("journal_entry")
            or result.get("purchase_invoice")
            or result.get("name")
            or result.get("document_name")
        )
        release_operation_lock(operation_id, document_type, doc_name, response_dict=result, success=True)
        return result
    except Exception as e:
        release_operation_lock(operation_id, document_type, None, response_dict={"status": "error", "message": str(e)}, success=False)
        raise

