import frappe
import json

def run():
    jv = frappe.get_doc("Journal Entry", "ACC-JV-2026-00014")
    print("COMPANY:", repr(jv.company))
    for acc in jv.accounts:
        print("ROW:", acc.account, "COST_CENTER:", repr(acc.cost_center))
    
    companies = frappe.db.get_all("Company", fields=["name", "company_name", "abbr", "default_currency", "cost_center"])
    cost_centers = frappe.db.get_all("Cost Center", fields=["name", "cost_center_name", "company"])
    print("COMPANIES:", json.dumps(companies, ensure_ascii=False))
    print("COST CENTERS:", json.dumps(cost_centers, ensure_ascii=False))

if __name__ == "__main__":
    frappe.init(site="erp.local")
    frappe.connect()
    run()
