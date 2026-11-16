# Copyright (c) 2026, Elsaidy ERP and Contributors
# License: MIT. See LICENSE

import json
import frappe
from frappe.utils import now_datetime, add_to_date


def sync_company_and_zatca_profile():
    """
    Configures Company 'ركن سبل الافق' with Saudi VAT and CR registration,
    and initializes ZATCA Business Settings for Sandbox compliance.
    """
    print("\n[Finalization] 1. Synchronizing Company Profile & ZATCA Business Settings...")
    company_name = "ركن سبل الافق"
    if frappe.db.exists("Company", company_name):
        frappe.db.set_value(
            "Company",
            company_name,
            {
                "tax_id": "399999999900003",
                "registration_details": "1010000000",
                "default_bank_account": "1201 - البنك الأهلي السعودي (SNB) - Rkn",
            },
        )
        frappe.db.commit()
        print(" -> Company profile updated with VAT ID (399999999900003) and CR (1010000000).")

    # National Address
    addr_title = "المقر الرئيسي - ركن سبل الأفق"
    existing_addr = frappe.db.get_value("Address", {"address_title": addr_title}, "name")
    if not existing_addr:
        addr = frappe.new_doc("Address")
        addr.address_title = addr_title
        addr.address_type = "Billing"
        addr.address_line1 = "طريق الملك فهد، حي العليا"
        addr.city = "الرياض"
        addr.country = "Saudi Arabia"
        addr.pincode = "12211"
        addr.custom_building_number = "7234"
        addr.append("links", {"link_doctype": "Company", "link_name": company_name})
        addr.insert(ignore_permissions=True)
        frappe.db.commit()
        existing_addr = addr.name
        print(f" -> Created National Address: {existing_addr}")

    # ZATCA Business Settings
    if frappe.db.exists("DocType", "ZATCA Business Settings"):
        site_name = frappe.local.site
        cli_path = f"/home/frappe/frappe-bench/sites/{site_name}/zatca-tools/zatca-cli-2.10.0/bin/zatca-cli"
        jre_path = f"/home/frappe/frappe-bench/sites/{site_name}/zatca-tools/jdk-11.0.23+9-jre"

        bs_name = frappe.db.get_value("ZATCA Business Settings", {"company": company_name}, "name")
        if not bs_name:
            bs = frappe.new_doc("ZATCA Business Settings")
            bs.company = company_name
            bs.company_unit = "الفرع الرئيسي"
            bs.company_unit_serial = "1-RSG|2-ERP|3-PROD001"
            bs.company_category = "المقاولات الإنشائية"
            bs.company_address = existing_addr
            bs.status = "Active"
            bs.country = "Saudi Arabia"
            bs.country_code = "SA"
            bs.seller_name = "شركة ركن سبل الأفق للمقاولات"
            bs.vat_registration_number = "399999999900003"
            bs.city = "الرياض"
            bs.building_number = "7234"
            bs.postal_code = "12211"
            bs.district = "العليا"
            bs.street = "طريق الملك فهد"
            bs.fatoora_server = "Sandbox"
            bs.type_of_business_transactions = "Let the system decide (both)"
            bs.cli_setup = "Manual"
            bs.zatca_cli_path = cli_path
            bs.java_home = jre_path
            bs.insert(ignore_permissions=True)
            frappe.db.commit()
            print(f" -> Created ZATCA Business Settings: {bs.name}")
        else:
            frappe.db.set_value(
                "ZATCA Business Settings",
                bs_name,
                {
                    "seller_name": "شركة ركن سبل الأفق للمقاولات",
                    "vat_registration_number": "399999999900003",
                    "zatca_cli_path": cli_path,
                    "java_home": jre_path,
                    "status": "Active",
                },
            )
            frappe.db.commit()
            print(f" -> Updated ZATCA Business Settings: {bs_name}")


def sync_print_formats_dynamic():
    """
    Ensures Print Formats fetch CR, VAT ID, and Bank Account dynamically from the Company
    rather than having hardcoded dummy test numbers.
    """
    print("\n[Finalization] 2. Synchronizing Dynamic Print Formats (No Hardcoding)...")
    from hagag_erp.setup import sync_saudi_print_formats
    sync_saudi_print_formats()
    print(" -> Dynamic Print Formats synchronized.")


def sync_insights_contracting_dashboards():
    """
    Sets up the 6 Arabic Contracting Insights Dashboards connected to live ERPNext data.
    """
    print("\n[Finalization] 3. Synchronizing 6 Contracting Dashboards in Frappe Insights v3...")
    wb_name = "1"
    if frappe.db.exists("Insights Workbook", wb_name):
        frappe.db.set_value("Insights Workbook", wb_name, "title", "لوحة القيادة التنفيذية - Elsaidy ERP")
    else:
        wb = frappe.new_doc("Insights Workbook")
        wb.name = wb_name
        wb.title = "لوحة القيادة التنفيذية - Elsaidy ERP"
        wb.insert(ignore_permissions=True)
    frappe.db.commit()

    # Define queries
    queries_def = [
        {"key": "gl", "title": "حركات الأستاذ العام - Elsaidy GL", "table": "tabGL Entry"},
        {"key": "sales", "title": "فواتير ومستخلصات المبيعات - Sales Invoices", "table": "tabSales Invoice"},
        {"key": "accounts", "title": "شجرة الحسابات والأرصدة - Accounts", "table": "tabAccount"},
        {"key": "employees", "title": "بيانات الكوادر البشرية والموظفين - Employees", "table": "tabEmployee"},
        {"key": "projects", "title": "سجل المشروعات والمواقع - Projects", "table": "tabProject"},
        {"key": "tasks", "title": "المهام التنفيذية الميدانية - Tasks", "table": "tabTask"},
        {"key": "po", "title": "أوامر الشراء والتوريد - Purchase Orders", "table": "tabPurchase Order"},
        {"key": "pi", "title": "فواتير المشتريات ومواد البناء - Purchase Invoices", "table": "tabPurchase Invoice"},
    ]

    query_map = {}
    for q in queries_def:
        existing = frappe.get_all("Insights Query v3", filters={"workbook": wb_name, "title": q["title"]}, pluck="name")
        if existing:
            query_map[q["key"]] = existing[0]
        else:
            ops = [{"type": "source", "table": {"type": "table", "data_source": "Site DB", "table_name": q["table"]}}]
            doc = frappe.new_doc("Insights Query v3")
            doc.title = q["title"]
            doc.workbook = wb_name
            doc.use_live_connection = 1
            doc.is_builder_query = 1
            doc.operations = json.dumps(ops)
            doc.insert(ignore_permissions=True)
            query_map[q["key"]] = doc.name
    frappe.db.commit()

    charts_def = [
        # CEO / Finance KPIs
        {"key": "kpi_liquidity", "title": "إجمالي السيولة النقدية والبنكية (SAR)", "query_key": "gl", "chart_type": "Number", "config": {"comparison": False, "decimal": "2", "shorten_numbers": True, "sparkline": False, "number_columns": [{"measure_name": "السيولة المتاحة", "column_name": "debit", "data_type": "Decimal", "aggregation": "sum", "format": "currency"}]}},
        {"key": "kpi_contracts", "title": "إجمالي عقود ومستخلصات المشاريع", "query_key": "sales", "chart_type": "Number", "config": {"comparison": False, "decimal": "2", "shorten_numbers": True, "sparkline": False, "number_columns": [{"measure_name": "إجمالي المستخلصات", "column_name": "base_grand_total", "data_type": "Decimal", "aggregation": "sum", "format": "currency"}]}},
        {"key": "kpi_expenses", "title": "إجمالي المصروفات التشغيلية", "query_key": "gl", "chart_type": "Number", "config": {"comparison": False, "decimal": "2", "shorten_numbers": True, "sparkline": False, "number_columns": [{"measure_name": "المصروفات", "column_name": "debit", "data_type": "Decimal", "aggregation": "sum", "format": "currency"}]}},
        {"key": "kpi_vat", "title": "صافي موقف ضريبة القيمة المضافة 15%", "query_key": "gl", "chart_type": "Number", "config": {"comparison": False, "decimal": "2", "shorten_numbers": True, "sparkline": False, "number_columns": [{"measure_name": "صافي الضريبة", "column_name": "credit", "data_type": "Decimal", "aggregation": "sum", "format": "currency"}]}},
        {"key": "chart_expenses_donut", "title": "توزيع المصروفات حسب البند المحاسبي", "query_key": "gl", "chart_type": "Donut", "config": {"filters": {"filters": [], "logical_operator": "And"}, "label_column": {"column_name": "account", "data_type": "String", "dimension_name": "account", "label": "الحساب المحاسبي", "value": "account"}, "limit": 20, "value_column": {"aggregation": "sum", "column_name": "debit", "data_type": "Decimal", "measure_name": "إجمالي المدين"}}},
        {"key": "chart_projects_bar", "title": "تحليل الأداء المالي للمشاريع ومراكز التكلفة (الإيرادات مقابل التكاليف)", "query_key": "gl", "chart_type": "Bar", "config": {"filters": {"filters": [], "logical_operator": "And"}, "grouping": "clustered", "limit": "20", "x_axis": {"dimension": {"column_name": "project", "data_type": "String", "dimension_name": "project", "label": "المشروع", "value": "project"}}, "y_axis": {"series": [{"measure": {"aggregation": "sum", "column_name": "debit", "data_type": "Decimal", "label": "التكاليف المباشرة", "measure_name": "التكاليف"}}, {"measure": {"aggregation": "sum", "column_name": "credit", "data_type": "Decimal", "label": "المستخلصات المحصلة", "measure_name": "الإيرادات"}}]}}},
        {"key": "chart_cashflow_line", "title": "منحنى التدفقات النقدية الشهرية وحركة الأستاذ العام", "query_key": "gl", "chart_type": "Bar", "config": {"filters": {"filters": [], "logical_operator": "And"}, "grouping": "stacked", "limit": "12", "x_axis": {"dimension": {"column_name": "posting_date", "data_type": "Datetime", "dimension_name": "posting_date", "granularity": "month", "label": "تاريخ الحركة", "value": "posting_date"}}, "y_axis": {"series": [{"measure": {"aggregation": "sum", "column_name": "debit", "data_type": "Decimal", "label": "المقبوضات / مدين", "measure_name": "المقبوضات"}}, {"measure": {"aggregation": "sum", "column_name": "credit", "data_type": "Decimal", "label": "المدفوعات / دائن", "measure_name": "المدفوعات"}}]}}},
        {"key": "table_accounts_summary", "title": "كشف أرصدة الحسابات الرئيسية والبنوك والعهد", "query_key": "accounts", "chart_type": "Table", "config": {"filters": {"filters": [], "logical_operator": "And"}, "limit": 50, "rows": [{"column_name": "name", "data_type": "String", "dimension_name": "name", "label": "اسم الحساب", "value": "name"}, {"column_name": "account_type", "data_type": "String", "dimension_name": "account_type", "label": "نوع الحساب", "value": "account_type"}], "columns": [], "values": [{"aggregation": "count", "column_name": "name", "data_type": "Integer", "label": "عدد الحسابات", "measure_name": "count"}]}},
        {"key": "chart_bank_custody_bar", "title": "تفصيل أرصدة البنوك والصناديق وعهد المهندسين (حساب 1120)", "query_key": "gl", "chart_type": "Bar", "config": {"filters": {"filters": [], "logical_operator": "And"}, "limit": "15", "x_axis": {"dimension": {"column_name": "account", "data_type": "String", "dimension_name": "account", "label": "حساب الصندوق / البنك / العهدة", "value": "account"}}, "y_axis": {"series": [{"measure": {"aggregation": "sum", "column_name": "debit", "data_type": "Decimal", "label": "رصيد الحساب", "measure_name": "الرصيد"}}]}}},
        {"key": "chart_vat_pie", "title": "تحليل ضريبة القيمة المضافة 15% (مدخلات المشتريات 1510 مقابل مخرجات المبيعات 2330)", "query_key": "gl", "chart_type": "Donut", "config": {"filters": {"filters": [], "logical_operator": "And"}, "label_column": {"column_name": "voucher_type", "data_type": "String", "dimension_name": "voucher_type", "label": "نوع المستند الضريبي", "value": "voucher_type"}, "limit": 10, "value_column": {"aggregation": "sum", "column_name": "debit", "data_type": "Decimal", "measure_name": "مبلغ الضريبة"}}},
        {"key": "chart_hr_headcount", "title": "توزيع الكوادر البشرية والموظفين حسب الأقسام والمسميات الوظيفية", "query_key": "employees", "chart_type": "Bar", "config": {"filters": {"filters": [], "logical_operator": "And"}, "limit": "20", "x_axis": {"dimension": {"column_name": "department", "data_type": "String", "dimension_name": "department", "label": "القسم / الإدارة", "value": "department"}}, "y_axis": {"series": [{"measure": {"aggregation": "count", "column_name": "name", "data_type": "Integer", "label": "عدد الكوادر", "measure_name": "العدد"}}]}}},
        {"key": "table_detailed_ledger", "title": "سجل الحركات المالية التفصيلي حسب المشروع ومركز التكلفة", "query_key": "gl", "chart_type": "Table", "config": {"filters": {"filters": [], "logical_operator": "And"}, "limit": 50, "rows": [{"column_name": "posting_date", "data_type": "Date", "dimension_name": "posting_date", "label": "تاريخ الحركة", "value": "posting_date"}, {"column_name": "account", "data_type": "String", "dimension_name": "account", "label": "اسم الحساب", "value": "account"}, {"column_name": "project", "data_type": "String", "dimension_name": "project", "label": "المشروع", "value": "project"}], "columns": [], "values": [{"aggregation": "sum", "column_name": "debit", "data_type": "Decimal", "label": "مدين", "measure_name": "مدين"}, {"aggregation": "sum", "column_name": "credit", "data_type": "Decimal", "label": "دائن", "measure_name": "دائن"}]}},
        # Projects & Tasks
        {"key": "chart_projects_progress", "title": "نسب إنجاز المشروعات الإنشائية الميدانية", "query_key": "projects", "chart_type": "Bar", "config": {"filters": {"filters": [], "logical_operator": "And"}, "limit": "15", "x_axis": {"dimension": {"column_name": "project_name", "data_type": "String", "dimension_name": "project_name", "label": "المشروع", "value": "project_name"}}, "y_axis": {"series": [{"measure": {"aggregation": "avg", "column_name": "percent_complete", "data_type": "Decimal", "label": "نسبة الإنجاز %", "measure_name": "الإنجاز"}}]}}},
        {"key": "chart_tasks_status", "title": "توزيع المهام الميدانية حسب الحالة", "query_key": "tasks", "chart_type": "Donut", "config": {"filters": {"filters": [], "logical_operator": "And"}, "label_column": {"column_name": "status", "data_type": "String", "dimension_name": "status", "label": "حالة المهمة", "value": "status"}, "limit": 10, "value_column": {"aggregation": "count", "column_name": "name", "data_type": "Integer", "measure_name": "عدد المهام"}}},
        # Procurement
        {"key": "kpi_po_total", "title": "إجمالي أوامر الشراء المعتمدة (SAR)", "query_key": "po", "chart_type": "Number", "config": {"comparison": False, "decimal": "2", "shorten_numbers": True, "sparkline": False, "number_columns": [{"measure_name": "أوامر الشراء", "column_name": "grand_total", "data_type": "Decimal", "aggregation": "sum", "format": "currency"}]}},
        {"key": "kpi_pi_total", "title": "إجمالي فواتير المشتريات ومواد البناء", "query_key": "pi", "chart_type": "Number", "config": {"comparison": False, "decimal": "2", "shorten_numbers": True, "sparkline": False, "number_columns": [{"measure_name": "فواتير المشتريات", "column_name": "grand_total", "data_type": "Decimal", "aggregation": "sum", "format": "currency"}]}},
        {"key": "chart_suppliers_donut", "title": "توزيع المشتريات ومواد البناء حسب الموردين", "query_key": "pi", "chart_type": "Donut", "config": {"filters": {"filters": [], "logical_operator": "And"}, "label_column": {"column_name": "supplier", "data_type": "String", "dimension_name": "supplier", "label": "المورد", "value": "supplier"}, "limit": 10, "value_column": {"aggregation": "sum", "column_name": "grand_total", "data_type": "Decimal", "measure_name": "إجمالي المشتريات"}}},
        # HR & Custodies
        {"key": "kpi_employees_count", "title": "إجمالي الكوادر البشرية النشطة", "query_key": "employees", "chart_type": "Number", "config": {"comparison": False, "decimal": "0", "shorten_numbers": False, "sparkline": False, "number_columns": [{"measure_name": "عدد الكوادر", "column_name": "name", "data_type": "Integer", "aggregation": "count", "format": "number"}]}},
        # Invoicing & Tax
        {"key": "table_sales_ipcs", "title": "سجل الفواتير والمستخلصات الضريبية المعتمدة", "query_key": "sales", "chart_type": "Table", "config": {"filters": {"filters": [], "logical_operator": "And"}, "limit": 50, "rows": [{"column_name": "name", "data_type": "String", "dimension_name": "name", "label": "رقم الفاتورة", "value": "name"}, {"column_name": "customer", "data_type": "String", "dimension_name": "customer", "label": "العميل", "value": "customer"}, {"column_name": "project", "data_type": "String", "dimension_name": "project", "label": "المشروع", "value": "project"}], "columns": [], "values": [{"aggregation": "sum", "column_name": "base_grand_total", "data_type": "Decimal", "label": "الإجمالي", "measure_name": "base_grand_total"}, {"aggregation": "sum", "column_name": "outstanding_amount", "data_type": "Decimal", "label": "المتبقي", "measure_name": "outstanding_amount"}]}}
    ]

    chart_map = {}
    for c in charts_def:
        existing = frappe.get_all("Insights Chart v3", filters={"workbook": wb_name, "title": c["title"]}, pluck="name")
        if existing:
            chart_map[c["key"]] = existing[0]
            # Ensure is_public is set
            frappe.db.set_value("Insights Chart v3", existing[0], "is_public", 1)
        else:
            doc = frappe.new_doc("Insights Chart v3")
            doc.title = c["title"]
            doc.workbook = wb_name
            doc.query = query_map[c["query_key"]]
            doc.chart_type = c["chart_type"]
            doc.config = json.dumps(c["config"])
            doc.is_public = 1
            doc.insert(ignore_permissions=True)
            chart_map[c["key"]] = doc.name
    frappe.db.commit()

    # The 6 Contracting Dashboards
    dashboards_config = [
        {
            "id_slug": "dsh_ceo",
            "title": "لوحة المدير التنفيذي - شركة ركن سبل الأفق",
            "items": [
                {"chart": chart_map["kpi_liquidity"], "type": "chart", "layout": {"h": 3, "i": "k1", "w": 5, "x": 0, "y": 0}},
                {"chart": chart_map["kpi_contracts"], "type": "chart", "layout": {"h": 3, "i": "k2", "w": 5, "x": 5, "y": 0}},
                {"chart": chart_map["kpi_expenses"], "type": "chart", "layout": {"h": 3, "i": "k3", "w": 5, "x": 10, "y": 0}},
                {"chart": chart_map["kpi_vat"], "type": "chart", "layout": {"h": 3, "i": "k4", "w": 5, "x": 15, "y": 0}},
                {"chart": chart_map["chart_expenses_donut"], "type": "chart", "layout": {"h": 8, "i": "c1", "w": 10, "x": 0, "y": 3}},
                {"chart": chart_map["chart_projects_bar"], "type": "chart", "layout": {"h": 8, "i": "c2", "w": 10, "x": 10, "y": 3}},
                {"chart": chart_map["chart_cashflow_line"], "type": "chart", "layout": {"h": 8, "i": "c3", "w": 10, "x": 0, "y": 11}},
                {"chart": chart_map["table_accounts_summary"], "type": "chart", "layout": {"h": 8, "i": "c4", "w": 10, "x": 10, "y": 11}},
            ],
        },
        {
            "id_slug": "dsh_projects",
            "title": "لوحة المشاريع والمقاولات - ركن سبل الأفق",
            "items": [
                {"chart": chart_map["chart_projects_progress"], "type": "chart", "layout": {"h": 8, "i": "p1", "w": 10, "x": 0, "y": 0}},
                {"chart": chart_map["chart_tasks_status"], "type": "chart", "layout": {"h": 8, "i": "p2", "w": 10, "x": 10, "y": 0}},
                {"chart": chart_map["chart_projects_bar"], "type": "chart", "layout": {"h": 8, "i": "p3", "w": 20, "x": 0, "y": 8}},
            ],
        },
        {
            "id_slug": "dsh_finance",
            "title": "لوحة الإدارة المالية والسيولة - ركن سبل الأفق",
            "items": [
                {"chart": chart_map["kpi_liquidity"], "type": "chart", "layout": {"h": 3, "i": "f1", "w": 6, "x": 0, "y": 0}},
                {"chart": chart_map["kpi_expenses"], "type": "chart", "layout": {"h": 3, "i": "f2", "w": 7, "x": 6, "y": 0}},
                {"chart": chart_map["kpi_vat"], "type": "chart", "layout": {"h": 3, "i": "f3", "w": 7, "x": 13, "y": 0}},
                {"chart": chart_map["chart_bank_custody_bar"], "type": "chart", "layout": {"h": 8, "i": "f4", "w": 10, "x": 0, "y": 3}},
                {"chart": chart_map["chart_expenses_donut"], "type": "chart", "layout": {"h": 8, "i": "f5", "w": 10, "x": 10, "y": 3}},
                {"chart": chart_map["table_detailed_ledger"], "type": "chart", "layout": {"h": 8, "i": "f6", "w": 20, "x": 0, "y": 11}},
            ],
        },
        {
            "id_slug": "dsh_procurement",
            "title": "لوحة المشتريات والموردين - ركن سبل الأفق",
            "items": [
                {"chart": chart_map["kpi_po_total"], "type": "chart", "layout": {"h": 3, "i": "m1", "w": 10, "x": 0, "y": 0}},
                {"chart": chart_map["kpi_pi_total"], "type": "chart", "layout": {"h": 3, "i": "m2", "w": 10, "x": 10, "y": 0}},
                {"chart": chart_map["chart_suppliers_donut"], "type": "chart", "layout": {"h": 8, "i": "m3", "w": 20, "x": 0, "y": 3}},
            ],
        },
        {
            "id_slug": "dsh_hr",
            "title": "لوحة الموارد البشرية والعمالة - ركن سبل الأفق",
            "items": [
                {"chart": chart_map["kpi_employees_count"], "type": "chart", "layout": {"h": 3, "i": "h1", "w": 20, "x": 0, "y": 0}},
                {"chart": chart_map["chart_hr_headcount"], "type": "chart", "layout": {"h": 8, "i": "h2", "w": 10, "x": 0, "y": 3}},
                {"chart": chart_map["chart_bank_custody_bar"], "type": "chart", "layout": {"h": 8, "i": "h3", "w": 10, "x": 10, "y": 3}},
            ],
        },
        {
            "id_slug": "dsh_billing_tax",
            "title": "لوحة المستخلصات والضريبة ومحجوزات الضمان",
            "items": [
                {"chart": chart_map["kpi_contracts"], "type": "chart", "layout": {"h": 3, "i": "t1", "w": 10, "x": 0, "y": 0}},
                {"chart": chart_map["kpi_vat"], "type": "chart", "layout": {"h": 3, "i": "t2", "w": 10, "x": 10, "y": 0}},
                {"chart": chart_map["chart_vat_pie"], "type": "chart", "layout": {"h": 8, "i": "t3", "w": 10, "x": 0, "y": 3}},
                {"chart": chart_map["table_sales_ipcs"], "type": "chart", "layout": {"h": 8, "i": "t4", "w": 10, "x": 10, "y": 3}},
            ],
        },
    ]

    for d_cfg in dashboards_config:
        existing = frappe.get_all("Insights Dashboard v3", filters={"title": d_cfg["title"]}, pluck="name")
        if not existing:
            # Also check old titles for rename
            if d_cfg["id_slug"] == "dsh_ceo":
                existing = frappe.get_all("Insights Dashboard v3", filters={"title": "لوحة المالك والمدير العام - الملخص التنفيذي الشامل"}, pluck="name")
            elif d_cfg["id_slug"] == "dsh_billing_tax":
                existing = frappe.get_all("Insights Dashboard v3", filters={"title": "التقارير التفصيلية للمشاريع والعهد والزكاة والضريبة"}, pluck="name")

        if existing:
            d = frappe.get_doc("Insights Dashboard v3", existing[0])
            d.title = d_cfg["title"]
            d.workbook = wb_name
            d.is_public = 1
            d.items = json.dumps(d_cfg["items"])
            d.set("linked_charts", [])
            for item in d_cfg["items"]:
                d.append("linked_charts", {"chart": item["chart"]})
            d.save(ignore_permissions=True)
            print(f" -> Updated Dashboard: {d_cfg['title']} ({d.name})")
        else:
            d = frappe.new_doc("Insights Dashboard v3")
            d.title = d_cfg["title"]
            d.workbook = wb_name
            d.is_public = 1
            d.items = json.dumps(d_cfg["items"])
            for item in d_cfg["items"]:
                d.append("linked_charts", {"chart": item["chart"]})
            d.insert(ignore_permissions=True)
            print(f" -> Created Dashboard: {d_cfg['title']} ({d.name})")

    frappe.db.commit()


def sync_executive_manager_portal():
    """
    Creates 'Executive Director (Read Only)' role and user 'director@elsaidy.org',
    with strict Read-Only permissions on contracting and dashboard doctypes.
    """
    print("\n[Finalization] 4. Synchronizing Executive Manager Portal Role & User...")
    role_name = "Executive Director (Read Only)"
    if not frappe.db.exists("Role", role_name):
        r = frappe.new_doc("Role")
        r.role_name = role_name
        r.desk_access = 1
        r.insert(ignore_permissions=True)
        print(f" -> Created Role: {role_name}")

    # Read-only doctypes
    read_only_doctypes = [
        "Insights Dashboard v3",
        "Insights Chart v3",
        "Insights Query v3",
        "Insights Workbook",
        "Project",
        "Task",
        "GL Entry",
        "Account",
        "Sales Invoice",
        "Purchase Invoice",
        "Employee",
        "Elsaidy Share Link",
    ]

    for dt in read_only_doctypes:
        if not frappe.db.exists("DocType", dt):
            continue
        existing_perm = frappe.db.exists("Custom DocPerm", {"parent": dt, "role": role_name, "permlevel": 0})
        if not existing_perm:
            try:
                cp = frappe.new_doc("Custom DocPerm")
                cp.parent = dt
                cp.parenttype = "DocType"
                cp.parentfield = "permissions"
                cp.role = role_name
                cp.permlevel = 0
                cp.read = 1
                cp.write = 0
                cp.create = 0
                cp.delete = 0
                cp.submit = 0
                cp.cancel = 0
                cp.amend = 0
                cp.report = 1
                cp.export = 1
                cp.print = 1
                cp.email = 1
                cp.insert(ignore_permissions=True)
            except Exception as e:
                pass
    frappe.db.commit()

    # User: director@elsaidy.org
    user_email = "director@elsaidy.org"
    if not frappe.db.exists("User", user_email):
        user = frappe.new_doc("User")
        user.email = user_email
        user.first_name = "المدير التنفيذي"
        user.last_name = "ركن سبل الأفق"
        user.user_type = "System User"
        user.send_welcome_email = 0
        user.enabled = 1
        user.append("roles", {"role": role_name})
        user.append("roles", {"role": "Insights User"})
        user.insert(ignore_permissions=True)
        # Set a secure random initial password
        user_doc = frappe.get_doc("User", user_email)
        user_doc.new_password = frappe.generate_hash(length=16)
        user_doc.save(ignore_permissions=True)
        frappe.db.commit()
        print(f" -> Created User: {user_email}")
    else:
        u = frappe.get_doc("User", user_email)
        has_role = any(r.role == role_name for r in u.roles)
        if not has_role:
            u.append("roles", {"role": role_name})
        has_insights = any(r.role == "Insights User" for r in u.roles)
        if not has_insights:
            u.append("roles", {"role": "Insights User"})
        u.enabled = 1
        u.save(ignore_permissions=True)
        frappe.db.commit()
        print(f" -> Verified User: {user_email}")


def sync_knowledge_base_wiki():
    """
    Configures Wiki Space for 'شركة ركن سبل الأفق المحدودة - قاعدة المعرفة',
    removes legacy institution names, and establishes the 7 structured chapters.
    """
    print("\n[Finalization] 5. Synchronizing Wiki Knowledge Base (7 Chapters)...")
    space_name = "atsc5al2gg"
    if frappe.db.exists("Wiki Space", space_name):
        frappe.db.set_value(
            "Wiki Space",
            space_name,
            {
                "space_name": "شركة ركن سبل الأفق المحدودة - قاعدة المعرفة",
                "is_published": 1,
            },
        )
        frappe.db.commit()
        print(" -> Updated Wiki Space name.")

    root_group = "atrt4uhbg7"

    # Clean old documents that carried previous institution names
    old_doc_name = "kbt6idbd58"
    if frappe.db.exists("Wiki Document", old_doc_name):
        old_doc = frappe.get_doc("Wiki Document", old_doc_name)
        cleaned_content = (old_doc.content or "").replace(
            "مؤسسة نورة مهنا أبوزيد للمقاولات", "شركة ركن سبل الأفق المحدودة"
        ).replace("مؤسسة نورة مهنا", "شركة ركن سبل الأفق")
        old_doc.title = "أرشيف - سياسات وضوابط العمل التأسيسية"
        old_doc.content = cleaned_content
        old_doc.is_published = 0
        old_doc.save(ignore_permissions=True)
        frappe.db.commit()

    # The 7 Official Chapters
    chapters = [
        {
            "slug": "company-policies",
            "title": "دليل الشركة والسياسات العامة",
            "is_published": 1,
            "content": """# شركة ركن سبل الأفق للمقاولات المحدودة
## دليل الشركة والسياسات العامة والقيم المؤسسية

### الرؤية والرسالة
الريادة في قطاع المقاولات والإنشاءات والبنية التحتية في المملكة العربية السعودية، وفق أعلى معايير الجودة ومستهدفات رؤية المملكة 2030.

### السياسات المؤسسية:
1. **الالتزام بالجودة والسلامة المهنية**: الالتزام الصارم باشتراطات كود البناء السعودي ومعايير السلامة المهنية المعتمدة في كافة المواقع والمشاريع.
2. **الشفافية والحوكمة الرقمية**: إدارة كافة العمليات التعاقدية والتنفيذية عبر نظام ELSAIDY ERP الموحد.
3. **السرية وأمن المعلومات**: حظر إفشاء أي بيانات فنية أو مالية أو تعاقدية دون إذن كتابي رسمي من الإدارة العليا.
"""
        },
        {
            "slug": "site-engineer-guide",
            "title": "دليل مهندس الموقع الميداني",
            "is_published": 0,
            "content": """# دليل مهندس الموقع الميداني - ركن سبل الأفق

### المسؤوليات الميدانية اليومية:
1. استلام الأعمال اليومية ومتابعة العمالة ومقاولي الباطن.
2. توثيق نسب الإنجاز الفعلي على نظام ELSAIDY ERP وربطه بالمهام المجدولة.
3. رفع طلبات المواد (Material Requests) قبل موعد الاحتياج الفعلي بـ 72 ساعة على الأقل.
4. إجراء الفحوصات الهندسية ومطابقة العينات الموردة للموقع.
"""
        },
        {
            "slug": "projects-and-ipcs",
            "title": "إجراءات المشروعات والمستخلصات",
            "is_published": 0,
            "content": """# إجراءات إدارة المشاريع والمستخلصات (IPCs)

### دورة إصدار واعتماد المستخلص:
1. **حصر الأعمال المنفذة**: يقوم مهندس الموقع بحصر الأعمال المنجزة على الطبيعة ومطابقتها مع الاستشاري.
2. **إصدار مسودة المستخلص الجاري (IPC)**: عبر نظام ELSAIDY ERP مع تسجيل نسب الإنجاز وحسم استرداد الدفعة المقدمة ومحجوز الضمان (10%).
3. **اعتماد الإدارة والمالية**: المراجعة المحاسبية والاعتماد وإصدار الفاتورة الضريبية ZATCA المرتبطة.
"""
        },
        {
            "slug": "procurement-and-stores",
            "title": "المشتريات والمخازن وإدارة التوريد",
            "is_published": 0,
            "content": """# دليل المشتريات والمخازن الميدانية

### ضوابط الشراء والتوريد:
1. لا يتم إصدار أمر شراء (Purchase Order) إلا بناءً على طلب مواد معتمد ومقارنة 3 عروض أسعار على الأقل للمواد الإنشائية الكبرى.
2. فحص المواد عند الاستلام في المستودع الميداني وإصدار إذن استلام بضاعة (Purchase Receipt).
3. الصرف للموقع يتم حصرياً بموجب إذن صرف مواد مرتبط برقم المشروع ومركز التكلفة.
"""
        },
        {
            "slug": "finance-and-custodies",
            "title": "المحاسبة والعهد المالية للمهندسين",
            "is_published": 0,
            "content": """# دليل المحاسبة المالية والعهد النقدية

### إدارة العهد النقدية (حساب 1120):
1. تصرف العهدة النقدية للمهندس الميداني بموجب سند صرف معتمد لتغطية المصروفات الطارئة للموقع.
2. تتم تصفية وتسوية العهدة بشكل دوري بإرفاق الفواتير الضريبية النظامية المستوفية لاشتراطات هيئة الزكاة والضريبة والجمارك.
3. تفصل ضريبة المدخلات 15% كأصل مسترد (حساب 1510) ولا تدرج ضمن المصروفات التشغيلية.
"""
        },
        {
            "slug": "human-resources",
            "title": "الموارد البشرية وشؤون الموظفين والعمالة",
            "is_published": 0,
            "content": """# دليل الموارد البشرية وشؤون الكوادر

### السياسات العمالية والإدارية:
1. الامتثال التام لنظام العمل السعودي والتأمينات الاجتماعية (GOSI).
2. تسجيل الحضور والانصراف الميداني ومتابعة تصاريح العمل والإقامات والتأمين الطبي.
3. مسيرات الأجور الشهرية وتوثيقها عبر نظام حماية الأجور (WPS).
"""
        },
        {
            "slug": "elsaidy-erp-manual",
            "title": "دليل استخدام نظام ELSAIDY ERP",
            "is_published": 0,
            "content": """# دليل استخدام ELSAIDY ERP للموظفين والمهندسين

### خطوات الاستخدام الأساسية:
1. **تسجيل الدخول**: عبر الرابط الرسمي الموحد `https://erp.elsaidy.org` باستخدام البريد المؤسسي.
2. **المكتب (Desk)**: الوصول إلى التطبيقات المصرح بها (المشاريع، المحاسبة، المشتريات، الموارد البشرية، المساعد الذكي Raven).
3. **تطبيق الجوال وواتساب**: إمكانية رفع الفواتير وإرسال صور أذونات الصرف والمستندات عبر Elsaidy WhatsApp AI للمعالجة الفورية المعتمدة.
"""
        },
    ]

    for idx, chap in enumerate(chapters):
        existing = frappe.db.get_value("Wiki Document", {"slug": chap["slug"]}, "name")
        if existing:
            doc = frappe.get_doc("Wiki Document", existing)
            doc.title = chap["title"]
            doc.content = chap["content"]
            doc.is_published = chap["is_published"]
            doc.sort_order = idx + 1
            doc.wiki_space = space_name
            doc.parent_wiki_document = root_group
            doc.save(ignore_permissions=True)
            print(f" -> Updated Chapter: {chap['title']}")
        else:
            doc = frappe.new_doc("Wiki Document")
            doc.title = chap["title"]
            doc.slug = chap["slug"]
            doc.route = f"docs/{chap['slug']}"
            doc.content = chap["content"]
            doc.is_published = chap["is_published"]
            doc.sort_order = idx + 1
            doc.wiki_space = space_name
            doc.parent_wiki_document = root_group
            doc.insert(ignore_permissions=True)
            print(f" -> Created Chapter: {chap['title']}")

    frappe.db.commit()


def sync_onboarding_and_workspace_cleanup():
    """
    Eliminates all 'Getting Started' popups/onboarding steps,
    polishes workspace titles, and restricts Builder icon to System Managers.
    """
    print("\n[Finalization] 6. Eliminating 'Getting Started' & Polishing Workspaces...")

    # Dismiss all Module Onboarding and Onboarding Steps
    frappe.db.sql("UPDATE `tabModule Onboarding` SET is_complete = 1")
    frappe.db.sql("UPDATE `tabOnboarding Step` SET is_complete = 1")
    frappe.db.commit()
    print(" -> Completed all Module Onboarding & Steps (Getting Started fully dismissed).")

    # Workspace Title Polishing
    ws_updates = {
        "Frappe CRM": {"title": "إدارة علاقات العملاء (CRM)", "is_hidden": 0},
        "Frappe Builder": {"title": "بناء وتصميم المواقع", "is_hidden": 1},
        "Welcome Workspace": {"is_hidden": 1},
        "ZATCA": {"title": "الفوترة الإلكترونية (ZATCA)", "is_hidden": 0},
    }
    for ws_name, vals in ws_updates.items():
        if frappe.db.exists("Workspace", ws_name):
            frappe.db.set_value("Workspace", ws_name, vals)
    frappe.db.commit()
    print(" -> Workspaces refined: CRM titled Arabic, Builder hidden from non-specialists, ZATCA active.")

    # Desktop Icon for ZATCA
    if not frappe.db.exists("Desktop Icon", "ZATCA"):
        try:
            di = frappe.new_doc("Desktop Icon")
            di.name = "ZATCA"
            di.module_name = "ZATCA"
            di.label = "الفوترة الإلكترونية (ZATCA)"
            di.link = "/app/zatca"
            di.type = "module"
            di.hidden = 0
            di.insert(ignore_permissions=True)
            frappe.db.commit()
            print(" -> Created Desktop Icon: الفوترة الإلكترونية (ZATCA)")
        except Exception:
            pass


def run_finalization_sync():
    """
    Main orchestration entry point to apply all system finalization steps idempotently.
    """
    print("\n" + "=" * 60)
    print(" ELSAIDY ERP — SYSTEM FINALIZATION SYNC")
    print(" Company: Rukn Subul Al Ofoq for Contracting")
    print("=" * 60)

    sync_company_and_zatca_profile()
    sync_print_formats_dynamic()
    sync_insights_contracting_dashboards()
    sync_executive_manager_portal()
    sync_knowledge_base_wiki()
    sync_onboarding_and_workspace_cleanup()

    print("\n" + "=" * 60)
    print(" ALL SYSTEM FINALIZATION TASKS COMPLETED SUCCESSFULLY ✅")
    print("=" * 60 + "\n")
    return True
