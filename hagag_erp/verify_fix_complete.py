import frappe
from hagag_erp.custody_service import get_employee_live_gl_balance

def run():
    target_user = "alyahmedelseidy@gmail.com"
    frappe.set_user(target_user)

    # 1. Test get_list
    emp_list = frappe.get_list("Employee", fields=["name", "employee_name", "company"])
    print(f"Employee list visible to {target_user} ({len(emp_list)}): {emp_list}")

    # 2. Test new doc permissions
    doc = frappe.new_doc("Employee")
    doc.first_name = "NewEmployeeTest"
    doc.company = "ركن سبل الافق"
    doc.check_permission("create")
    print("New Employee check_permission('create'): SUCCESS")

    # 3. Check HR-EMP-00001 data and live GL balance
    frappe.set_user("Administrator")
    emp1 = frappe.get_doc("Employee", "HR-EMP-00001")
    print(f"HR-EMP-00001 intact: name={emp1.name}, employee_name={emp1.employee_name}, user_id={emp1.user_id}")
    
    gl_bal = get_employee_live_gl_balance("HR-EMP-00001")
    print(f"Live GL Custody balance of HR-EMP-00001: {gl_bal.get('posted_custody_balance')} SAR")
    assert gl_bal.get("posted_custody_balance") == 2185.0, f"Balance mismatch: {gl_bal}"
    print("ALL VERIFICATIONS PASSED 100%!")

if __name__ == "__main__":
    frappe.init(site="erp.local")
    frappe.connect()
    run()
