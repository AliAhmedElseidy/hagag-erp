import frappe
import json

def run():
    vouchers = ["ACC-JV-2026-00014", "ACC-JV-2026-00015", "ACC-JV-2026-00016", "ACC-JV-2026-00017"]
    
    # Check attached files
    files = frappe.db.get_all(
        "File",
        filters={"attached_to_name": ["in", vouchers]},
        fields=["name", "file_name", "file_url", "attached_to_doctype", "attached_to_name", "file_size"]
    )
    
    # Inspect accounts balance
    target_accounts = [
        "1110 - نقد - Rkn",
        "1120 - عهد نقدية للمهندسين والمشرفين - Rkn",
        "1201 - البنك الأهلي السعودي (SNB) - Rkn",
        "1510 - ضريبة القيمة المضافة للمدخلات 15% - Rkn",
        "1610 - سلف الموظفين - Rkn",
        "5120 - مصروف الوقود والمحروقات - Rkn"
    ]
    
    account_balances = {}
    for acc in target_accounts:
        gl = frappe.db.sql("""
            SELECT SUM(debit) as total_debit, SUM(credit) as total_credit
            FROM `tabGL Entry`
            WHERE account = %s AND is_cancelled = 0
        """, (acc,), as_dict=True)[0]
        deb = float(gl.total_debit or 0)
        crd = float(gl.total_credit or 0)
        account_balances[acc] = {
            "debit": deb,
            "credit": crd,
            "net_debit_balance": round(deb - crd, 2)
        }
        
    # Check employee custody balance in GL specifically
    emp_custody_gl = frappe.db.sql("""
        SELECT SUM(debit) as total_debit, SUM(credit) as total_credit
        FROM `tabGL Entry`
        WHERE party_type = 'Employee' AND party = 'HR-EMP-00001' AND account LIKE '1120%' AND is_cancelled = 0
    """, as_dict=True)[0]
    emp_deb = float(emp_custody_gl.total_debit or 0)
    emp_crd = float(emp_custody_gl.total_credit or 0)
    emp_custody_balance = round(emp_deb - emp_crd, 2)
    
    # Check Bank Account doctypes
    bank_accounts = frappe.db.get_all(
        "Bank Account",
        fields=["name", "account_name", "bank", "account", "is_company_account"]
    )
    
    # Check Bank Clearance / Reconciliation for SNB 1201
    bank_gl = frappe.db.get_all(
        "GL Entry",
        filters={"account": "1201 - البنك الأهلي السعودي (SNB) - Rkn", "is_cancelled": 0},
        fields=["name", "posting_date", "voucher_type", "voucher_no", "debit", "credit", "is_opening"]
    )
    
    # Check if any other transfer of 2000 SAR exists anywhere
    transfers_2000 = frappe.db.sql("""
        SELECT jv.name, jv.posting_date, jv.docstatus, jv.total_debit, jv.user_remark
        FROM `tabJournal Entry` jv
        WHERE jv.total_debit = 2000.0
    """, as_dict=True)
    
    res = {
        "attached_files": files,
        "account_balances": account_balances,
        "emp_custody_balance": emp_custody_balance,
        "bank_accounts": bank_accounts,
        "bank_gl": bank_gl,
        "transfers_2000": [dict(t) for t in transfers_2000]
    }
    
    print("STAGE2_AUDIT_START")
    print(json.dumps(res, indent=2, ensure_ascii=False, default=str))
    print("STAGE2_AUDIT_END")
    return res
