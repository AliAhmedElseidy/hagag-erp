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


def rewrite(html):
    m = ver("manifest/manifest.webmanifest")
    new = "/assets/hagag_erp/manifest/manifest.webmanifest?v=" + m
    old = "/assets/hrms/frontend/manifest.webmanifest"
    html = html.replace(old, new)
    html = html.replace("<title>Frappe HR</title>", "<title>Hagag HR</title>")
    t = 'apple-mobile-web-app-title" content="'
    html = html.replace(t + "Frappe HR", t + "Hagag HR")
    return html.replace("</head>", tags() + "</head>", 1)


def inject(response, request):
    try:
        if not request.path.startswith("/hrms"):
            return
        if response.status_code != 200 or response.mimetype != "text/html":
            return
        html = response.get_data(as_text=True)
        if "hagag_hrms.css" in html or "</head>" not in html:
            return
        response.set_data(rewrite(html))
    except Exception:
        frappe.logger("hagag_erp").exception("hrms inject failed")
