import hashlib
import os

import frappe

BASE = os.path.join(os.path.dirname(__file__), "public")
CACHE = {}


def ver(rel):
    if rel not in CACHE:
        try:
            with open(os.path.join(BASE, rel), "rb") as f:
                CACHE[rel] = hashlib.md5(f.read()).hexdigest()[:8]
        except Exception:
            CACHE[rel] = "0"
    return CACHE[rel]


def tags():
    css = ver("css/hagag_hrms.css")
    js = ver("js/hagag_hrms.js")
    a = '<link rel="stylesheet" '
    a += 'href="/assets/hagag_erp/css/hagag_hrms.css?v=' + css + '">'
    b = '<script src="/assets/hagag_erp/js/hagag_hrms.js?v='
    b += js + '" defer></script>'
    return a + b


def inject(response, request):
    try:
        if not request.path.startswith("/hrms"):
            return
        if response.status_code != 200 or response.mimetype != "text/html":
            return
        html = response.get_data(as_text=True)
        if "hagag_hrms.css" in html or "</head>" not in html:
            return
        response.set_data(html.replace("</head>", tags() + "</head>", 1))
    except Exception:
        frappe.logger("hagag_erp").exception("hrms inject failed")
