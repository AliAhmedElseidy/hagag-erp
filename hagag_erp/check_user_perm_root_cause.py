import frappe
from frappe.permissions import has_user_permission, get_user_permissions

def test():
    user = "alyahmedelseidy@gmail.com"
    frappe.set_user(user)
    
    user_perms = get_user_permissions(user)
    print("USER PERMISSIONS CACHE:", user_perms)
    
    mock_emp = frappe.new_doc("Employee")
    mock_emp.first_name = "TestEmp"
    mock_emp.company = "ركن سبل الافق"
    
    hup = has_user_permission(mock_emp, user)
    print("has_user_permission(mock_emp):", hup)
    
    # What if applicable_for is set, or what if Employee restriction is removed?
    # Let's inspect the User Permission record for Employee:
    up_record = frappe.db.get_value("User Permission", {"user": user, "allow": "Employee"}, ["name", "for_value", "apply_to_all_doctypes", "applicable_for"], as_dict=True)
    print("UP RECORD FOR EMPLOYEE:", up_record)
    
    # What does ERPNext/Frappe HR documentation say about User Permission on Employee?
    # When an employee user is given a User Permission on Employee = 'HR-EMP-00001',
    # if it applies to DocType 'Employee' with apply_to_all_doctypes = 1,
    # the user is prevented from seeing OR CREATING other employees!
    # But this user is HR Manager and System Manager!
    # For an HR Manager, should they be restricted to ONLY their own Employee record in DocType Employee?
    # NO! If they are restricted to their own Employee record, they cannot view other employees or create employees!
    # OR: The User Permission on Employee should have `applicable_for` set to child doctypes/documents (like Expense Claim, Leave Application, Attendance) BUT NOT Employee itself!
    # OR: In User Permission, there is "Applicable For":
    # If `applicable_for` is set, the User Permission ONLY applies to specific DocTypes (e.g. Leave Application, Expense Claim, etc.), OR
    # Is User Permission on Employee even needed for HR Manager / System Manager?
    
    frappe.set_user("Administrator")

if __name__ == "__main__":
    frappe.init(site="erp.local")
    frappe.connect()
    test()
