import frappe
from hagag_erp.custody_service import get_employee_live_gl_balance, notify_employee_custody_event
import json

def run():
    results = {}
    
    # Step 1: Cancel ACC-JV-2026-00017
    jv17 = frappe.get_doc("Journal Entry", "ACC-JV-2026-00017")
    if jv17.docstatus == 1:
        jv17.cancel()
        results["cancel_jv17"] = {
            "status": "cancelled",
            "docstatus": jv17.docstatus
        }
    else:
        results["cancel_jv17"] = {
            "status": "already_cancelled",
            "docstatus": jv17.docstatus
        }
        
    # Check balance after cancellation
    bal_after_cancel = get_employee_live_gl_balance("HR-EMP-00001")
    results["balance_after_cancel"] = bal_after_cancel
    
    # Step 2: Create correct replacement Journal Entry
    company = "ركن سبل الافق"
    cost_center = "رئيسي - Rkn"
    
    new_jv = frappe.new_doc("Journal Entry")
    new_jv.voucher_type = "Journal Entry"
    new_jv.company = company
    new_jv.posting_date = frappe.utils.nowdate()
    new_jv.cheque_date = frappe.utils.nowdate()
    new_jv.cheque_no = "TRF-SNB-2000"
    new_jv.user_remark = "تغذية عهدة نقدية للمهندس علي أحمد الصعيدي (HR-EMP-00001) بتحويل من البنك الأهلي السعودي - تصحيح بديل للقيد الملغى ACC-JV-2026-00017"
    
    # Row 1: Custody Debit
    new_jv.append("accounts", {
        "account": "1120 - عهد نقدية للمهندسين والمشرفين - Rkn",
        "party_type": "Employee",
        "party": "HR-EMP-00001",
        "debit_in_account_currency": 2000.0,
        "credit_in_account_currency": 0.0,
        "cost_center": cost_center
    })
    
    # Row 2: Bank Credit
    new_jv.append("accounts", {
        "account": "1201 - البنك الأهلي السعودي (SNB) - Rkn",
        "debit_in_account_currency": 0.0,
        "credit_in_account_currency": 2000.0,
        "cost_center": cost_center
    })
    
    new_jv.insert(ignore_permissions=True)
    new_jv.submit()
    
    results["new_jv"] = {
        "name": new_jv.name,
        "docstatus": new_jv.docstatus,
        "posting_date": str(new_jv.posting_date),
        "total_debit": new_jv.total_debit,
        "total_credit": new_jv.total_credit
    }
    
    # Step 3: Check final balances
    bal_after_replacement = get_employee_live_gl_balance("HR-EMP-00001")
    results["balance_after_replacement"] = bal_after_replacement
    
    # Step 4: Outbound WhatsApp notification using standard document hook
    notif_res = notify_employee_custody_event(new_jv)
    results["notification_result"] = notif_res
    
    # Step 5: Full verification of GL entries for 1110, 1120, 1201, 1510, 1610, 5120
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
    results["final_account_balances"] = account_balances
    
    frappe.db.commit()
    print("STAGE2_CORRECTION_SUCCESS")
    print(json.dumps(results, indent=2, ensure_ascii=False, default=str))
    return results

if __name__ == "__main__":
    frappe.init(site="erp.local")
    frappe.connect()
    run()
