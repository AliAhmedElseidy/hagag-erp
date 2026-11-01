import base64

import frappe
from hagag_erp.whatsapp_bridge import call_baileys_api, normalize_phone_number, require_hub_permission


@frappe.whitelist()
def send_invoice_whatsapp(invoice_name, mobile):
    require_hub_permission("write")
    invoice = frappe.get_doc("Sales Invoice", invoice_name)
    invoice.check_permission("read")
    phone = normalize_phone_number(mobile)
    if not phone or not 9 <= len(phone) <= 15:
        frappe.throw("رقم المستلم غير صالح")
    pdf = frappe.get_print("Sales Invoice", invoice_name, as_pdf=True)
    return call_baileys_api("send", method="POST", data={
        "number": phone,
        "message": "فاتورتك رقم " + invoice_name + " من الصعيدي للمقاولات",
        "pdf_base64": base64.b64encode(pdf).decode(),
        "filename": invoice_name + ".pdf",
    })
