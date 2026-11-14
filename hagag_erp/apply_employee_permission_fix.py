import frappe
from frappe.permissions import has_permission, get_doc_permissions

def apply_fix():
    print("=" * 70)
    print("APPLYING PRECISE USER PERMISSION FIX FOR HR MANAGER")
    print("=" * 70)

    target_user = "alyahmedelseidy@gmail.com"
    up_id = "o4f3kdtu3r"

    # 1. Verify existence of the conflicting User Permission
    if not frappe.db.exists("User Permission", up_id):
        # Look by filters
        up_id = frappe.db.get_value("User Permission", {"user": target_user, "allow": "Employee"}, "name")
        if not up_id:
            print("No conflicting User Permission found on Employee for", target_user)
            return

    up_doc = frappe.get_doc("User Permission", up_id)
    print(f"Found Conflicting User Permission: {up_doc.name}")
    print(f"  User: {up_doc.user} | Allow: {up_doc.allow} | For Value: {up_doc.for_value}")
    
    # Ensure it's for Employee
    assert up_doc.allow == "Employee", f"Expected allow == 'Employee', got {up_doc.allow}"
    assert up_doc.user == target_user, f"Expected user == {target_user}, got {up_doc.user}"

    # 2. Delete the conflicting User Permission document using standard Frappe API
    frappe.delete_doc("User Permission", up_doc.name, force=1)
    print(f"Successfully deleted User Permission [{up_doc.name}].")

    # 3. Clear permission caches
    frappe.clear_cache(user=target_user)
    frappe.clear_cache(doctype="Employee")
    print("Cleared user and doctype caches.")

    # 4. Verify Company User Permission remains intact
    comp_up = frappe.db.get_value(
        "User Permission",
        {"user": target_user, "allow": "Company"},
        ["name", "for_value"],
        as_dict=True
    )
    print(f"Company User Permission intact: {comp_up}")
    assert comp_up and comp_up.for_value == "ركن سبل الافق", "Company User Permission missing!"

    # 5. Verify Employee HR-EMP-00001 is completely untouched
    emp1 = frappe.db.get_value(
        "Employee",
        "HR-EMP-00001",
        ["name", "employee_name", "status", "company", "user_id"],
        as_dict=True
    )
    print(f"Employee HR-EMP-00001 data intact: {emp1}")
    assert emp1 and emp1.name == "HR-EMP-00001" and emp1.user_id == target_user

    # 6. Test permission check for target_user
    frappe.set_user(target_user)
    
    # A. Check doctype level
    dt_create = has_permission("Employee", ptype="create", user=target_user)
    print(f"Permission check on DocType 'Employee' (create): {dt_create}")
    assert dt_create is True, "Expected dt_create to be True!"

    # B. Check new doc creation permission
    mock_emp = frappe.new_doc("Employee")
    mock_emp.first_name = "VerificationWorker"
    mock_emp.company = "ركن سبل الافق"
    mock_emp.gender = "Male"
    mock_emp.date_of_birth = "1995-01-01"
    mock_emp.date_of_joining = "2026-01-01"

    doc_create = has_permission("Employee", doc=mock_emp, ptype="create", user=target_user)
    print(f"Permission check on new doc (create): {doc_create}")
    assert doc_create is True, "Expected doc_create to be True!"

    # C. Test mock_emp.check_permission('create')
    mock_emp.check_permission("create")
    print("mock_emp.check_permission('create'): PASSED without any exceptions!")

    # D. Test simulation insert in transaction rollback
    frappe.db.savepoint("verify_insert")
    mock_emp.insert()
    print(f"Test insert succeeded! Document name would be: {mock_emp.name}")
    frappe.db.rollback(save_point="verify_insert")
    print("Rollback verification successful. ZERO mock records created in production.")

    # 7. Commit the User Permission removal
    frappe.db.commit()
    frappe.set_user("Administrator")
    print("\n" + "=" * 70)
    print("PRECISE FIX COMPLETED AND COMMITTED SUCCESSFULLY")
    print("=" * 70)

if __name__ == "__main__":
    frappe.init(site="erp.local")
    frappe.connect()
    apply_fix()
