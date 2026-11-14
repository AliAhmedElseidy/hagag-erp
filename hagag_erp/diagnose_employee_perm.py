import frappe
import json

def run_diagnostics():
    print("=" * 70)
    print("DIAGNOSING EMPLOYEE PERMISSION ISSUE IN ERPNEXT V16")
    print("=" * 70)

    # 1. Active User
    user_id = "alyahmedelseidy@gmail.com"
    roles = frappe.get_roles(user_id)
    print(f"\nTarget User: {user_id}")
    print(f"Has Roles ({len(roles)}): {roles}")
    print(f"Is System Manager: {'System Manager' in roles}")
    print(f"Is HR Manager: {'HR Manager' in roles}")
    print(f"Is HR User: {'HR User' in roles}")

    # 2. Standard DocPerm for Employee
    print("\n--- STANDARD DOCPERM FOR EMPLOYEE ---")
    std_perms = frappe.db.sql("""
        SELECT * FROM `tabDocPerm` WHERE parent = 'Employee'
    """, as_dict=True)
    for p in std_perms:
        print(f"  Role: {p.role:22} | Level: {p.permlevel} | C:{p.get('create')} R:{p.get('read')} W:{p.get('write')} D:{p.get('delete')} | if_owner:{p.get('if_owner')}")

    # 3. Custom DocPerm for Employee
    print("\n--- CUSTOM DOCPERM FOR EMPLOYEE ---")
    custom_perms = frappe.db.sql("""
        SELECT * FROM `tabCustom DocPerm` WHERE parent = 'Employee'
    """, as_dict=True)
    if custom_perms:
        for p in custom_perms:
            print(f"  [CUSTOM] Role: {p.role:22} | Level: {p.permlevel} | C:{p.get('create')} R:{p.get('read')} W:{p.get('write')} D:{p.get('delete')} | if_owner:{p.get('if_owner')}")
    else:
        print("  No Custom DocPerm records for Employee.")

    # 4. User Permissions (Restrictions) for Target User
    print(f"\n--- USER PERMISSIONS FOR {user_id} ---")
    user_perms = frappe.db.get_all(
        "User Permission",
        filters={"user": user_id},
        fields=["name", "user", "allow", "for_value", "is_default", "apply_to_all_doctypes", "applicable_for"]
    )
    if user_perms:
        for up in user_perms:
            print(f"  Allow: {up.allow:15} | For: {up.for_value:25} | ApplyAll: {up.apply_to_all_doctypes} | ApplicableFor: {up.applicable_for}")
    else:
        print("  No User Permission restrictions found for this user.")

    # Also check if any User Permission exists for ANY user on Employee or Company
    all_up = frappe.db.sql("""
        SELECT user, allow, for_value, apply_to_all_doctypes, applicable_for
        FROM `tabUser Permission`
    """, as_dict=True)
    print(f"\n--- ALL USER PERMISSIONS IN SYSTEM ({len(all_up)}) ---")
    for up in all_up:
        print(f"  User: {up.user:25} | Allow: {up.allow:15} | For: {up.for_value}")

    # 5. Hooks on Employee
    print("\n--- HOOKS ON PERMISSIONS & EMPLOYEE ---")
    hooks = frappe.get_hooks()
    has_perm_hooks = hooks.get("has_permission", {})
    perm_query_hooks = hooks.get("permission_query_conditions", {})
    doc_events = hooks.get("doc_events", {}).get("Employee", {})
    override_classes = hooks.get("override_doctype_class", {})

    print(f"  has_permission hooks: {json.dumps(has_perm_hooks, indent=2)}")
    print(f"  permission_query_conditions hooks: {json.dumps(perm_query_hooks, indent=2)}")
    print(f"  doc_events for Employee: {json.dumps(doc_events, indent=2)}")
    print(f"  override_doctype_class: {json.dumps(override_classes, indent=2)}")

    # 6. Check exact error in Error Log
    print("\n--- RECENT ERROR LOGS ---")
    errs = frappe.db.sql("""
        SELECT name, method, error, creation
        FROM `tabError Log`
        WHERE error LIKE '%Employee%' OR error LIKE '%Permission%' OR method LIKE '%Employee%'
        ORDER BY creation DESC
        LIMIT 5
    """, as_dict=True)
    for err in errs:
        print(f"\nError Log {err.name} [{err.creation}] in {err.method}:")
        print(err.error[:500])

    # 7. Testing Permission Execution & Backtrace
    print("\n--- DETAILED PERMISSION RESOLUTION FOR EMPLOYEE ---")
    frappe.set_user(user_id)
    
    can_create = frappe.has_permission("Employee", ptype="create")
    can_read = frappe.has_permission("Employee", ptype="read")
    can_write = frappe.has_permission("Employee", ptype="write")
    print(f"frappe.has_permission('Employee'): create={can_create}, read={can_read}, write={can_write}")

    # Test creating document
    new_emp = frappe.new_doc("Employee")
    new_emp.first_name = "TestEmpPerm"
    new_emp.company = "ركن سبل الافق"
    new_emp.gender = "Male"
    new_emp.date_of_birth = "1990-01-01"
    new_emp.date_of_joining = "2026-01-01"
    
    can_create_doc = frappe.has_permission(doc=new_emp, ptype="create")
    print(f"frappe.has_permission(doc=new_emp, 'create'): {can_create_doc}")

    # Let's inspect get_doc_permissions
    from frappe.permissions import get_doc_permissions
    doc_perms = get_doc_permissions(new_emp, user=user_id)
    print(f"get_doc_permissions(new_emp): {doc_perms}")

    # Let's test new_emp.check_permission("create")
    try:
        new_emp.check_permission("create")
        print("new_emp.check_permission('create'): SUCCESS!")
    except Exception as e:
        import traceback
        print("new_emp.check_permission('create') FAILED:")
        print(traceback.format_exc())

    # Let's test insert simulation in transaction rollback mode
    print("\n--- SIMULATING new_emp.insert() ---")
    try:
        # We start a savepoint or rollback
        frappe.db.savepoint("test_emp_perm")
        new_emp.insert()
        print("new_emp.insert() SUCCESS! Doc name:", new_emp.name)
        frappe.db.rollback(save_point="test_emp_perm")
        print("Rollback successful. ZERO records created.")
    except Exception as e:
        import traceback
        print("new_emp.insert() FAILED:")
        print(traceback.format_exc())
        frappe.db.rollback(save_point="test_emp_perm")

    frappe.set_user("Administrator")

if __name__ == "__main__":
    frappe.init(site="erp.local")
    frappe.connect()
    run_diagnostics()
