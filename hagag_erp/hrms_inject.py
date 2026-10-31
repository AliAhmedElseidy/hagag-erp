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


def whitelabel_tags():
    css = ver("css/elsaidy_whitelabel.css")
    js = ver("js/elsaidy_whitelabel.js")
    tags = f'<link rel="stylesheet" href="/assets/hagag_erp/css/elsaidy_whitelabel.css?v={css}">'
    tags += f'<script src="/assets/hagag_erp/js/elsaidy_whitelabel.js?v={js}" defer></script>'
    return tags


def rewrite_html(html, path=""):
    # Manifest rewrite
    m = ver("manifest/manifest.webmanifest")
    new_manifest = f"/assets/hagag_erp/manifest/manifest.webmanifest?v={m}"
    html = html.replace("/assets/hrms/frontend/manifest.webmanifest", new_manifest)

    # Title replacements
    html = html.replace("<title>Frappe HR</title>", "<title>Elsaidy HR</title>")
    html = html.replace("<title>Hagag HR</title>", "<title>Elsaidy HR</title>")
    html = html.replace("<title>Frappe CRM</title>", "<title>Elsaidy CRM</title>")
    html = html.replace("<title>Hagag CRM</title>", "<title>Elsaidy CRM</title>")
    html = html.replace("<title>Frappe Helpdesk</title>", "<title>Elsaidy Support</title>")
    html = html.replace("<title>Frappe Insights</title>", "<title>Elsaidy BI & Insights</title>")

    t = 'apple-mobile-web-app-title" content="'
    html = html.replace(t + "Frappe HR", t + "Elsaidy HR")
    html = html.replace(t + "Hagag HR", t + "Elsaidy HR")
    html = html.replace(t + "Frappe CRM", t + "Elsaidy CRM")
    html = html.replace(t + "Frappe Helpdesk", t + "Elsaidy Support")

    if "elsaidy_whitelabel.css" not in html and "</head>" in html:
        html = html.replace("</head>", whitelabel_tags() + "</head>", 1)
    return html


def inject(response, request):
    try:
        if response.status_code != 200 or response.mimetype != "text/html":
            return

        path = request.path or ""
        spa_prefixes = ("/hrms", "/crm", "/helpdesk", "/insights", "/raven", "/app", "/desk")
        if not any(path.startswith(prefix) for prefix in spa_prefixes):
            return

        html = response.get_data(as_text=True)
        if "elsaidy_whitelabel.css" in html or "</head>" not in html:
            return
        response.set_data(rewrite_html(html, path))
    except Exception:
        frappe.logger("hagag_erp").exception("spa whitelabel inject failed")
