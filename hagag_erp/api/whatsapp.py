import base64
import requests
import frappe

WA_TOKEN = "HAGAG_WA_7f3c9a2d6e4b8a1c"

@frappe.whitelist()
def send_invoice_whatsapp(invoice_name, mobile):
    mobile = mobile.strip().replace(" ", "").replace("-", "")
    if mobile.startswith("00"):
        mobile = mobile[2:]
    elif mobile.startswith("0") and len(mobile) == 10:
        mobile = "966" + mobile[1:]
    pdf = frappe.get_print("Sales Invoice", invoice_name, as_pdf=True)
    pdf_b64 = base64.b64encode(pdf).decode()
    r = requests.post(
        "http://wa-baileys:3000/send",
        headers={"Authorization": "Bearer " + WA_TOKEN},
        json={
            "number": mobile,
            "message": "فاتورتك رقم " + invoice_name + " من حجاج للمقاولات",
            "pdf_base64": pdf_b64,
            "filename": invoice_name + ".pdf"
        },
        timeout=30
    )
    return r.json()
