import base64

import frappe

from hagag_erp.whatsapp_bridge import call_baileys_api


@frappe.whitelist()
def send_invoice_whatsapp(invoice_name, mobile):
	mobile = mobile.strip().replace(" ", "").replace("-", "")
	if mobile.startswith("00"):
		mobile = mobile[2:]
	elif mobile.startswith("0") and len(mobile) == 10:
		mobile = "966" + mobile[1:]
	pdf = frappe.get_print("Sales Invoice", invoice_name, as_pdf=True)
	pdf_b64 = base64.b64encode(pdf).decode("ascii")
	return call_baileys_api(
		"send",
		method="POST",
		data={
			"number": mobile,
			"message": f"فاتورتك رقم {invoice_name} من شركة ركن سبل الأفق المحدودة",
			"pdf_base64": pdf_b64,
			"filename": f"{invoice_name}.pdf",
		},
	)
