import frappe
import json

def get_expense_accounts():
    accounts = frappe.db.sql("""
        SELECT name, account_name, account_number, account_type, company, parent_account, is_group
        FROM `tabAccount`
        WHERE root_type = 'Expense'
        ORDER BY account_number ASC, name ASC
    """, as_dict=True)
    print("EXPENSE_ACCOUNTS_START")
    print(json.dumps([dict(a) for a in accounts], indent=2, ensure_ascii=False))
    print("EXPENSE_ACCOUNTS_END")

if __name__ == "__main__":
    frappe.init(site="erp.local")
    frappe.connect()
    get_expense_accounts()
