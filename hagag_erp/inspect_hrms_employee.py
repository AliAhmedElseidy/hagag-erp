import frappe
import inspect

def run():
    doc_class = frappe.get_doc("DocType", "Employee").get_controller()
    print("Employee Controller:", doc_class)
    methods = [m for m in dir(doc_class) if "permission" in m.lower() or "user" in m.lower()]
    print("Methods related to permission/user:", methods)
    for m in methods:
        try:
            print(f"\n--- Method: {m} ---")
            print(inspect.getsource(getattr(doc_class, m)))
        except Exception as e:
            print(f"Could not get source for {m}: {e}")

    # Check User Permission records on Employee
    ups = frappe.db.get_all("User Permission", filters={"allow": "Employee"}, fields=["*"])
    print("\n--- ALL USER PERMISSIONS FOR EMPLOYEE ---")
    for u in ups:
        print(f"Name: {u.name} | User: {u.user} | For: {u.for_value} | apply_to_all_doctypes: {u.apply_to_all_doctypes} | applicable_for: {u.applicable_for}")

if __name__ == "__main__":
    frappe.init(site="erp.local")
    frappe.connect()
    run()
