# Copyright (c) 2026, Elsaidy ERP and Contributors
# License: MIT. See LICENSE

import frappe
from hagag_erp.dashboard_api import get_shared_dashboard_data


def get_context(context):
    context.no_cache = 1
    token = frappe.form_dict.get("token")
    context.title = "بوابة المشاهدة التنفيذية - ELSAIDY ERP"

    if not token:
        context.error = "لم يتم تحديد رمز الوصول (Token). يرجى استخدام الرابط الكامل المرسل إليكم."
        return

    try:
        data = get_shared_dashboard_data(token)
        context.data = data
        context.dashboard_title = data.get("title")
        context.metrics = data.get("metrics")
        context.projects = data.get("projects")
        context.departments = data.get("departments")
        context.expires_at = data.get("expires_at")
        context.views_count = data.get("views_count")
    except Exception as e:
        context.error = str(e)
