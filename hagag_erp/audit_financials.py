import frappe
import json

def run_audit():
    docs = ["ACC-JV-2026-00014", "ACC-JV-2026-00015", "ACC-JV-2026-00016", "ACC-JV-2026-00017"]

    output = []
    for docname in docs:
        if not frappe.db.exists("Journal Entry", docname):
            output.append({"name": docname, "exists": False})
            continue
        jv = frappe.get_doc("Journal Entry", docname)
        accounts = []
        for acc in jv.accounts:
            accounts.append({
                "account": acc.account,
                "party_type": acc.party_type,
                "party": acc.party,
                "debit": float(acc.debit_in_account_currency or 0),
                "credit": float(acc.credit_in_account_currency or 0)
            })
        gl_entries = frappe.db.get_all(
            "GL Entry",
            filters={"voucher_no": docname, "is_cancelled": 0},
            fields=["name", "account", "party_type", "party", "debit", "credit", "posting_date"]
        )
        wa_logs = frappe.db.get_all(
            "Elsaidy WhatsApp Log",
            filters={"linked_document_name": docname},
            fields=["name", "direction", "status", "receiver_phone", "reply_text", "creation"]
        )
        output.append({
            "name": jv.name,
            "posting_date": str(jv.posting_date),
            "creation": str(jv.creation),
            "docstatus": jv.docstatus,
            "user_remark": jv.user_remark,
            "accounts": accounts,
            "gl_entries": [dict(g) for g in gl_entries],
            "wa_logs": [dict(w) for w in wa_logs]
        })

    # All GL entries for 1120 or HR-EMP-00001
    emp_gl = frappe.db.sql("""
        SELECT gl.name, gl.posting_date, gl.voucher_type, gl.voucher_no, gl.account, gl.party_type, gl.party, gl.debit, gl.credit, gl.is_cancelled, gl.creation
        FROM `tabGL Entry` gl
        WHERE gl.party = 'HR-EMP-00001' OR gl.account LIKE '1120%'
        ORDER BY gl.posting_date ASC, gl.creation ASC
    """, as_dict=True)

    # All Journal Entries currently existing
    all_jvs = frappe.db.sql("""
        SELECT name, posting_date, docstatus, user_remark, total_debit, total_credit, creation
        FROM `tabJournal Entry`
        ORDER BY creation ASC
    """, as_dict=True)

    # Let's inspect the Chart of Accounts for Bank accounts and Cash accounts in Company Rkn
    banks = frappe.db.sql("""
        SELECT name, account_name, account_number, parent_account, root_type, account_type, is_group
        FROM `tabAccount`
        WHERE company LIKE '%Rkn%' AND (account_type IN ('Bank', 'Cash') OR account_name LIKE '%أهلي%' OR account_name LIKE '%بنك%' OR account_number LIKE '111%')
        ORDER BY account_number ASC
    """, as_dict=True)

    result = {
        "target_docs": output,
        "all_gl_for_emp_or_1120": [dict(r) for r in emp_gl],
        "all_journal_entries": [dict(j) for j in all_jvs],
        "bank_and_cash_accounts": [dict(b) for b in banks]
    }
    
    print("AUDIT_RESULT_START")
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    print("AUDIT_RESULT_END")
    return result

if __name__ == "__main__":
    frappe.init(site="erp.local")
    frappe.connect()
    run_audit()
