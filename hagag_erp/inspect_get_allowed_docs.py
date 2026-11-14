import frappe
import inspect
from frappe import permissions

def run():
    print(inspect.getsource(permissions.get_allowed_docs_for_doctype))

if __name__ == "__main__":
    frappe.init(site="erp.local")
    frappe.connect()
    run()
