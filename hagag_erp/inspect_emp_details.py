import frappe

def run():
    emp = frappe.db.get_value(
        "Employee",
        "HR-EMP-00001",
        ["name", "employee_name", "user_id", "create_user_permission", "company"],
        as_dict=True
    )
    print("HR-EMP-00001 DETAILS:", emp)

if __name__ == "__main__":
    frappe.init(site="erp.local")
    frappe.connect()
    run()
