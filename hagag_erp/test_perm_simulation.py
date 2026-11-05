import frappe
from frappe.permissions import has_permission, get_doc_permissions

def run():
    user = "alyahmedelseidy@gmail.com"
    frappe.set_user(user)
    
    # 1. Inspect UP record
    up_record = frappe.db.get_value(
        "User Permission",
        {"user": user, "allow": "Employee"},
        ["name", "creation", "modified", "owner", "modified_by", "for_value", "apply_to_all_doctypes", "applicable_for"],
        as_dict=True
    )
    print("UP RECORD:", up_record)
    
    # 2. Check child tables of User Permission
    up_doc = frappe.get_doc("User Permission", up_record.name)
    print("UP DOC FIELDS:", up_doc.as_dict())

    # 3. Test what happens if this User Permission is temporarily bypassed or deleted in a transaction savepoint!
    frappe.db.savepoint("test_perm_fix")
    
    # Try deleting or modifying the UP
    frappe.db.delete("User Permission", {"name": up_record.name})
    frappe.clear_cache(user=user)
    
    # Now check permissions
    can_create_dt = has_permission("Employee", ptype="create", user=user)
    mock_emp = frappe.new_doc("Employee")
    mock_emp.first_name = "TestEngineer"
    mock_emp.company = "ركن سبل الافق"
    mock_emp.gender = "Male"
    mock_emp.date_of_birth = "1992-05-10"
    mock_emp.date_of_joining = "2026-01-01"
    
    can_create_doc = has_permission("Employee", doc=mock_emp, ptype="create", user=user)
    doc_perms = get_doc_permissions(mock_emp, user=user)
    
    print("\n--- RESULTS WITHOUT USER PERMISSION ON EMPLOYEE ---")
    print(f"has_permission('Employee', 'create'): {can_create_dt}")
    print(f"has_permission(doc=mock_emp, 'create'): {can_create_doc}")
    print(f"get_doc_permissions(mock_emp): {doc_perms}")
    
    try:
        mock_emp.check_permission("create")
        print("mock_emp.check_permission('create'): PASSED!")
    except Exception as e:
        print("mock_emp.check_permission('create'): FAILED ->", e)

    try:
        mock_emp.insert()
        print(f"mock_emp.insert(): SUCCESS! Created {mock_emp.name}")
    except Exception as e:
        print("mock_emp.insert(): FAILED ->", e)

    # Check if user can still read their own employee HR-EMP-00001
    can_read_own = has_permission(doc="HR-EMP-00001", ptype="read", user=user, doctype="Employee")
    can_write_own = has_permission(doc="HR-EMP-00001", ptype="write", user=user, doctype="Employee")
    print(f"Access to own HR-EMP-00001: read={can_read_own}, write={can_write_own}")

    # Rollback savepoint completely!
    frappe.db.rollback(save_point="test_perm_fix")
    print("\nRollback complete. DB unchanged.")
    
    frappe.set_user("Administrator")

if __name__ == "__main__":
    frappe.init(site="erp.local")
    frappe.connect()
    run()
