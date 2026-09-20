import frappe

CSS = '<link rel="stylesheet" href="/assets/hagag_erp/css/hagag_hrms.css">'
JS = '<script src="/assets/hagag_erp/js/hagag_hrms.js" defer></script>'


def inject(response, request):
    try:
        if not request.path.startswith("/hrms"):
            return
        if response.status_code != 200 or response.mimetype != "text/html":
            return
        html = response.get_data(as_text=True)
        if "hagag_hrms.css" in html or "</head>" not in html:
            return
        response.set_data(html.replace("</head>", CSS + JS + "</head>", 1))
    except Exception:
        frappe.logger("hagag_erp").exception("hrms inject failed")
