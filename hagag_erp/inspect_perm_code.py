import frappe
import inspect
from frappe import permissions

def run():
    print("=== has_user_permission source ===")
    if hasattr(permissions, "has_user_permission"):
        print(inspect.getsource(permissions.has_user_permission))
        
    print("\n=== get_user_permissions source ===")
    if hasattr(permissions, "get_user_permissions"):
        print(inspect.getsource(permissions.get_user_permissions))

    print("\n=== has_permission source ===")
    if hasattr(permissions, "has_permission"):
        print(inspect.getsource(permissions.has_permission))

if __name__ == "__main__":
    frappe.init(site="erp.local")
    frappe.connect()
    run()
