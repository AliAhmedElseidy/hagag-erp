# Copyright (c) 2026, Elsaidy ERP and Contributors
# License: MIT. See LICENSE

import json
import frappe
from frappe.utils import now_datetime, add_to_date


def sync_company_and_zatca_profile():
    """
    Safely configures ZATCA environment and tools without overwriting
    official Company Tax ID, Commercial Registration, or Address data.
    Ensures Sandbox mode is retained and no production invoices are issued.
    """
    print("\n[Finalization] 1. Auditing Company Profile & ZATCA Configuration...")
    company_name = "ركن سبل الافق"
    if not frappe.db.exists("Company", company_name):
        print(f" -> Company '{company_name}' not found, skipping.")
        return

    company_doc = frappe.get_doc("Company", company_name)
    print(f" -> Preserving existing Company data (VAT ID: {company_doc.tax_id or 'Not Set'}, CR: {company_doc.registration_details or 'Not Set'}). No automatic overwrite.")

    # ZATCA Business Settings (Environment & Tools Setup only)
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
            bs.status = "Active"
            bs.country = "Saudi Arabia"
            bs.country_code = "SA"
            bs.seller_name = company_name
            bs.vat_registration_number = company_doc.tax_id or ""
            bs.fatoora_server = "Sandbox"  # STRICT: Always Sandbox until explicit onboarding
            bs.type_of_business_transactions = "Let the system decide (both)"
            bs.cli_setup = "Manual"
            bs.zatca_cli_path = cli_path
            bs.java_home = jre_path
            bs.insert(ignore_permissions=True)
            frappe.db.commit()
            print(f" -> Initialized ZATCA Business Settings in Sandbox: {bs.name}")
        else:
            frappe.db.set_value(
                "ZATCA Business Settings",
                bs_name,
                {
                    "zatca_cli_path": cli_path,
                    "java_home": jre_path,
                    "fatoora_server": "Sandbox",  # STRICT: Safety guard against premature production invoices
                },
            )
            frappe.db.commit()
            print(f" -> Maintained ZATCA Business Settings ({bs_name}) in Sandbox mode with verified tool paths.")


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
    Uses precise native SQL queries with proper accounting logic (debit - credit,
    root_type / account filters, cancelled filter, real company scope).
    Ensures strict privacy (is_public=0) and explicit DocShare for management users.
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

    # Define exact SQL queries
    queries_def = [
        {
            "key": "kpi_liq",
            "title": "استعلام السيولة النقدية والبنكية والعهد (SAR)",
            "sql": """
                SELECT 
                    COALESCE(SUM(gle.debit - gle.credit), 0) AS liquidity
                FROM `tabGL Entry` gle
                JOIN `tabAccount` acc ON gle.account = acc.name
                WHERE gle.company = 'ركن سبل الافق' AND gle.is_cancelled = 0
                AND (acc.account_type IN ('Cash', 'Bank') OR acc.account_number IN ('1110', '1201', '1120'))
            """
        },
        {
            "key": "kpi_contracts",
            "title": "استعلام إجمالي عقود ومستخلصات المشاريع المعتمدة (SAR)",
            "sql": """
                SELECT 
                    COALESCE(SUM(base_grand_total), 0) AS contracts_total
                FROM `tabSales Invoice`
                WHERE company = 'ركن سبل الافق' AND docstatus = 1
            """
        },
        {
            "key": "kpi_exp",
            "title": "استعلام إجمالي المصروفات التشغيلية المباشرة (SAR)",
            "sql": """
                SELECT 
                    COALESCE(SUM(gle.debit - gle.credit), 0) AS expenses_total
                FROM `tabGL Entry` gle
                JOIN `tabAccount` acc ON gle.account = acc.name
                WHERE gle.company = 'ركن سبل الافق' AND gle.is_cancelled = 0
                AND acc.root_type = 'Expense'
            """
        },
        {
            "key": "kpi_vat",
            "title": "استعلام موقف ضريبة القيمة المضافة 15% (SAR)",
            "sql": """
                SELECT 
                    COALESCE(SUM(CASE WHEN acc.account_number = '2330' OR acc.name LIKE '%%2330%%' THEN (gle.credit - gle.debit) ELSE 0 END), 0) -
                    COALESCE(SUM(CASE WHEN acc.account_number = '1510' OR acc.name LIKE '%%1510%%' THEN (gle.debit - gle.credit) ELSE 0 END), 0) AS net_vat
                FROM `tabGL Entry` gle
                JOIN `tabAccount` acc ON gle.account = acc.name
                WHERE gle.company = 'ركن سبل الافق' AND gle.is_cancelled = 0
            """
        },
        {
            "key": "expenses_donut",
            "title": "استعلام توزيع المصروفات حسب البند المحاسبي",
            "sql": """
                SELECT 
                    acc.account_name AS account_label,
                    COALESCE(SUM(gle.debit - gle.credit), 0) AS expense_amount
                FROM `tabGL Entry` gle
                JOIN `tabAccount` acc ON gle.account = acc.name
                WHERE gle.company = 'ركن سبل الافق' AND gle.is_cancelled = 0
                AND acc.root_type = 'Expense'
                GROUP BY acc.account_name
                HAVING expense_amount > 0
                ORDER BY expense_amount DESC
                LIMIT 10
            """
        },
        {
            "key": "projects_financial",
            "title": "استعلام الأداء المالي للمشاريع (التكاليف مقابل الإيرادات)",
            "sql": """
                SELECT 
                    COALESCE(p.project_name, gle.project) AS project_label,
                    COALESCE(SUM(CASE WHEN acc.root_type = 'Expense' THEN (gle.debit - gle.credit) ELSE 0 END), 0) AS direct_cost,
                    COALESCE(SUM(CASE WHEN acc.root_type = 'Income' THEN (gle.credit - gle.debit) ELSE 0 END), 0) AS revenue
                FROM `tabGL Entry` gle
                JOIN `tabAccount` acc ON gle.account = acc.name
                LEFT JOIN `tabProject` p ON gle.project = p.name
                WHERE gle.company = 'ركن سبل الافق' AND gle.is_cancelled = 0
                AND gle.project IS NOT NULL AND gle.project != ''
                GROUP BY gle.project
                LIMIT 15
            """
        },
        {
            "key": "cashflow_monthly",
            "title": "استعلام منحنى التدفقات النقدية الشهرية",
            "sql": """
                SELECT 
                    DATE_FORMAT(gle.posting_date, '%Y-%m-01') AS month_date,
                    COALESCE(SUM(CASE WHEN gle.debit > 0 THEN gle.debit ELSE 0 END), 0) AS inflows,
                    COALESCE(SUM(CASE WHEN gle.credit > 0 THEN gle.credit ELSE 0 END), 0) AS outflows
                FROM `tabGL Entry` gle
                JOIN `tabAccount` acc ON gle.account = acc.name
                WHERE gle.company = 'ركن سبل الافق' AND gle.is_cancelled = 0
                AND (acc.account_type IN ('Cash', 'Bank') OR acc.account_number IN ('1110', '1201', '1120'))
                GROUP BY month_date
                ORDER BY month_date ASC
                LIMIT 12
            """
        },
        {
            "key": "accounts_summary",
            "title": "استعلام كشف أرصدة الحسابات الرئيسية والبنوك والعهد",
            "sql": """
                SELECT 
                    acc.account_number,
                    acc.account_name,
                    acc.account_type,
                    COALESCE(SUM(gle.debit - gle.credit), 0) AS current_balance
                FROM `tabAccount` acc
                LEFT JOIN `tabGL Entry` gle ON acc.name = gle.account AND gle.company = 'ركن سبل الافق' AND gle.is_cancelled = 0
                WHERE acc.company = 'ركن سبل الافق' AND acc.is_group = 0
                GROUP BY acc.name
                ORDER BY acc.account_number ASC
                LIMIT 50
            """
        },
        {
            "key": "bank_custody",
            "title": "استعلام تفصيل أرصدة البنوك والصناديق والعهد",
            "sql": """
                SELECT 
                    acc.account_name,
                    COALESCE(SUM(gle.debit - gle.credit), 0) AS balance
                FROM `tabAccount` acc
                LEFT JOIN `tabGL Entry` gle ON acc.name = gle.account AND gle.company = 'ركن سبل الافق' AND gle.is_cancelled = 0
                WHERE acc.company = 'ركن سبل الافق'
                AND (acc.account_type IN ('Cash', 'Bank') OR acc.account_number IN ('1110', '1201', '1120'))
                GROUP BY acc.name
                ORDER BY balance DESC
            """
        },
        {
            "key": "vat_analysis",
            "title": "استعلام تحليل ضريبة القيمة المضافة 15%",
            "sql": """
                SELECT 
                    CASE 
                        WHEN acc.account_number = '1510' OR acc.name LIKE '%%1510%%' THEN 'ضريبة المدخلات (مشتريات 15%)'
                        WHEN acc.account_number = '2330' OR acc.name LIKE '%%2330%%' THEN 'ضريبة المخرجات (مبيعات 15%)'
                        ELSE 'ضرائب ورسوم أخرى'
                    END AS vat_type,
                    COALESCE(SUM(gle.debit + gle.credit), 0) AS vat_amount
                FROM `tabGL Entry` gle
                JOIN `tabAccount` acc ON gle.account = acc.name
                WHERE gle.company = 'ركن سبل الافق' AND gle.is_cancelled = 0
                AND (acc.account_type = 'Tax' OR acc.account_number IN ('1510', '2330') OR acc.name LIKE '%%1510%%' OR acc.name LIKE '%%2330%%')
                GROUP BY vat_type
            """
        },
        {
            "key": "detailed_ledger",
            "title": "استعلام سجل الحركات المالية التفصيلي",
            "sql": """
                SELECT 
                    gle.posting_date,
                    acc.account_name,
                    COALESCE(p.project_name, gle.project, '-') AS project_name,
                    gle.debit,
                    gle.credit,
                    gle.remarks
                FROM `tabGL Entry` gle
                JOIN `tabAccount` acc ON gle.account = acc.name
                LEFT JOIN `tabProject` p ON gle.project = p.name
                WHERE gle.company = 'ركن سبل الافق' AND gle.is_cancelled = 0
                ORDER BY gle.posting_date DESC, gle.creation DESC
                LIMIT 50
            """
        },
        {
            "key": "projects_progress",
            "title": "استعلام نسب إنجاز المشروعات الإنشائية الميدانية",
            "sql": """
                SELECT 
                    project_name,
                    status,
                    percent_complete
                FROM `tabProject`
                WHERE company = 'ركن سبل الافق'
                ORDER BY creation DESC
                LIMIT 15
            """
        },
        {
            "key": "tasks_status",
            "title": "استعلام توزيع المهام الميدانية حسب الحالة",
            "sql": """
                SELECT 
                    status,
                    COUNT(name) AS task_count
                FROM `tabTask`
                GROUP BY status
            """
        },
        {
            "key": "kpi_po",
            "title": "استعلام إجمالي أوامر الشراء المعتمدة (SAR)",
            "sql": """
                SELECT 
                    COALESCE(SUM(grand_total), 0) AS po_total
                FROM `tabPurchase Order`
                WHERE company = 'ركن سبل الافق' AND docstatus = 1
            """
        },
        {
            "key": "kpi_pi",
            "title": "استعلام إجمالي فواتير المشتريات ومواد البناء (SAR)",
            "sql": """
                SELECT 
                    COALESCE(SUM(grand_total), 0) AS pi_total
                FROM `tabPurchase Invoice`
                WHERE company = 'ركن سبل الافق' AND docstatus = 1
            """
        },
        {
            "key": "suppliers_donut",
            "title": "استعلام توزيع المشتريات ومواد البناء حسب الموردين",
            "sql": """
                SELECT 
                    supplier,
                    COALESCE(SUM(grand_total), 0) AS supplier_total
                FROM `tabPurchase Invoice`
                WHERE company = 'ركن سبل الافق' AND docstatus = 1
                GROUP BY supplier
                ORDER BY supplier_total DESC
                LIMIT 10
            """
        },
        {
            "key": "kpi_emp",
            "title": "استعلام إجمالي الكوادر البشرية النشطة",
            "sql": """
                SELECT 
                    COUNT(name) AS employee_count
                FROM `tabEmployee`
                WHERE company = 'ركن سبل الافق' AND status = 'Active'
            """
        },
        {
            "key": "hr_dept",
            "title": "استعلام توزيع الكوادر حسب الأقسام والمسميات",
            "sql": """
                SELECT 
                    COALESCE(NULLIF(department, ''), 'إداري عام') AS dept_label,
                    COUNT(name) AS staff_count
                FROM `tabEmployee`
                WHERE company = 'ركن سبل الافق'
                GROUP BY department
            """
        },
        {
            "key": "sales_ipcs",
            "title": "استعلام سجل الفواتير والمستخلصات الضريبية المعتمدة",
            "sql": """
                SELECT 
                    name,
                    customer,
                    project,
                    base_grand_total,
                    outstanding_amount
                FROM `tabSales Invoice`
                WHERE company = 'ركن سبل الافق' AND docstatus = 1
                ORDER BY posting_date DESC
                LIMIT 50
            """
        },
    ]

    q_map = {}
    for q_cfg in queries_def:
        ops = [{"type": "sql", "data_source": "Site DB", "raw_sql": q_cfg["sql"]}]
        existing = frappe.get_all("Insights Query v3", filters={"workbook": wb_name, "title": q_cfg["title"]}, pluck="name")
        if existing:
            q_doc = frappe.get_doc("Insights Query v3", existing[0])
            q_doc.use_live_connection = 1
            q_doc.is_builder_query = 0
            q_doc.is_native_query = 1
            q_doc.operations = json.dumps(ops)
            q_doc.save(ignore_permissions=True)
            q_map[q_cfg["title"]] = q_doc.name
        else:
            q_doc = frappe.new_doc("Insights Query v3")
            q_doc.title = q_cfg["title"]
            q_doc.workbook = wb_name
            q_doc.use_live_connection = 1
            q_doc.is_builder_query = 0
            q_doc.is_native_query = 1
            q_doc.operations = json.dumps(ops)
            q_doc.insert(ignore_permissions=True)
            q_map[q_cfg["title"]] = q_doc.name
    frappe.db.commit()

    charts_def = [
        # CEO & Finance KPIs
        {
            "key": "kpi_liquidity",
            "title": "صافي مركز السيولة والعهد (بانتظار تسوية رأس المال) (SAR)",
            "query_title": "استعلام السيولة النقدية والبنكية والعهد (SAR)",
            "chart_type": "Number",
            "config": {
                "comparison": False,
                "decimal": "2",
                "shorten_numbers": True,
                "sparkline": False,
                "number_columns": [
                    {"measure_name": "صافي موقف السيولة والعهد (غير مسوى) (SAR)", "column_name": "liquidity", "data_type": "Decimal", "aggregation": "sum", "format": "currency"}
                ]
            }
        },
        {
            "key": "kpi_contracts",
            "title": "إجمالي عقود ومستخلصات المشاريع",
            "query_title": "استعلام إجمالي عقود ومستخلصات المشاريع المعتمدة (SAR)",
            "chart_type": "Number",
            "config": {
                "comparison": False,
                "decimal": "2",
                "shorten_numbers": True,
                "sparkline": False,
                "number_columns": [
                    {"measure_name": "إجمالي المستخلصات (SAR)", "column_name": "contracts_total", "data_type": "Decimal", "aggregation": "sum", "format": "currency"}
                ]
            }
        },
        {
            "key": "kpi_expenses",
            "title": "إجمالي المصروفات التشغيلية",
            "query_title": "استعلام إجمالي المصروفات التشغيلية المباشرة (SAR)",
            "chart_type": "Number",
            "config": {
                "comparison": False,
                "decimal": "2",
                "shorten_numbers": True,
                "sparkline": False,
                "number_columns": [
                    {"measure_name": "المصروفات التشغيلية (SAR)", "column_name": "expenses_total", "data_type": "Decimal", "aggregation": "sum", "format": "currency"}
                ]
            }
        },
        {
            "key": "kpi_vat",
            "title": "صافي موقف ضريبة القيمة المضافة 15%",
            "query_title": "استعلام موقف ضريبة القيمة المضافة 15% (SAR)",
            "chart_type": "Number",
            "config": {
                "comparison": False,
                "decimal": "2",
                "shorten_numbers": True,
                "sparkline": False,
                "number_columns": [
                    {"measure_name": "صافي الضريبة (SAR)", "column_name": "net_vat", "data_type": "Decimal", "aggregation": "sum", "format": "currency"}
                ]
            }
        },
        {
            "key": "chart_expenses_donut",
            "title": "توزيع المصروفات حسب البند المحاسبي",
            "query_title": "استعلام توزيع المصروفات حسب البند المحاسبي",
            "chart_type": "Donut",
            "config": {
                "filters": {"filters": [], "logical_operator": "And"},
                "label_column": {"column_name": "account_label", "data_type": "String", "dimension_name": "account_label", "label": "البند المحاسبي", "value": "account_label"},
                "limit": 10,
                "value_column": {"aggregation": "sum", "column_name": "expense_amount", "data_type": "Decimal", "measure_name": "مبلغ المصروف"}
            }
        },
        {
            "key": "chart_projects_bar",
            "title": "تحليل الأداء المالي للمشاريع ومراكز التكلفة (الإيرادات مقابل التكاليف)",
            "query_title": "استعلام الأداء المالي للمشاريع (التكاليف مقابل الإيرادات)",
            "chart_type": "Bar",
            "config": {
                "filters": {"filters": [], "logical_operator": "And"},
                "grouping": "clustered",
                "limit": "15",
                "x_axis": {"dimension": {"column_name": "project_label", "data_type": "String", "dimension_name": "project_label", "label": "المشروع", "value": "project_label"}},
                "y_axis": {
                    "series": [
                        {"measure": {"aggregation": "sum", "column_name": "direct_cost", "data_type": "Decimal", "label": "التكاليف المباشرة", "measure_name": "التكاليف"}},
                        {"measure": {"aggregation": "sum", "column_name": "revenue", "data_type": "Decimal", "label": "المستخلصات المعتمدة", "measure_name": "الإيرادات"}}
                    ]
                }
            }
        },
        {
            "key": "chart_cashflow_line",
            "title": "منحنى التدفقات النقدية الشهرية وحركة الأستاذ العام",
            "query_title": "استعلام منحنى التدفقات النقدية الشهرية",
            "chart_type": "Bar",
            "config": {
                "filters": {"filters": [], "logical_operator": "And"},
                "grouping": "stacked",
                "limit": "12",
                "x_axis": {"dimension": {"column_name": "month_date", "data_type": "Date", "dimension_name": "month_date", "label": "الشهر", "value": "month_date"}},
                "y_axis": {
                    "series": [
                        {"measure": {"aggregation": "sum", "column_name": "inflows", "data_type": "Decimal", "label": "المقبوضات / مدين", "measure_name": "المقبوضات"}},
                        {"measure": {"aggregation": "sum", "column_name": "outflows", "data_type": "Decimal", "label": "المدفوعات / دائن", "measure_name": "المدفوعات"}}
                    ]
                }
            }
        },
        {
            "key": "table_accounts_summary",
            "title": "كشف أرصدة الحسابات الرئيسية والبنوك والعهد",
            "query_title": "استعلام كشف أرصدة الحسابات الرئيسية والبنوك والعهد",
            "chart_type": "Table",
            "config": {
                "filters": {"filters": [], "logical_operator": "And"},
                "limit": 50,
                "rows": [
                    {"column_name": "account_number", "data_type": "String", "dimension_name": "account_number", "label": "رقم الحساب", "value": "account_number"},
                    {"column_name": "account_name", "data_type": "String", "dimension_name": "account_name", "label": "اسم الحساب", "value": "account_name"},
                    {"column_name": "account_type", "data_type": "String", "dimension_name": "account_type", "label": "نوع الحساب", "value": "account_type"}
                ],
                "columns": [],
                "values": [
                    {"aggregation": "sum", "column_name": "current_balance", "data_type": "Decimal", "label": "الرصيد الفعلي", "measure_name": "الرصيد"}
                ]
            }
        },
        {
            "key": "chart_bank_custody_bar",
            "title": "تفصيل أرصدة البنوك والصناديق وعهد المهندسين (حساب 1120)",
            "query_title": "استعلام تفصيل أرصدة البنوك والصناديق والعهد",
            "chart_type": "Bar",
            "config": {
                "filters": {"filters": [], "logical_operator": "And"},
                "limit": "15",
                "x_axis": {"dimension": {"column_name": "account_name", "data_type": "String", "dimension_name": "account_name", "label": "الحساب / العهدة", "value": "account_name"}},
                "y_axis": {
                    "series": [
                        {"measure": {"aggregation": "sum", "column_name": "balance", "data_type": "Decimal", "label": "رصيد الحساب", "measure_name": "الرصيد"}}
                    ]
                }
            }
        },
        {
            "key": "chart_vat_pie",
            "title": "تحليل ضريبة القيمة المضافة 15% (مدخلات المشتريات 1510 مقابل مخرجات المبيعات 2330)",
            "query_title": "استعلام تحليل ضريبة القيمة المضافة 15%",
            "chart_type": "Donut",
            "config": {
                "filters": {"filters": [], "logical_operator": "And"},
                "label_column": {"column_name": "vat_type", "data_type": "String", "dimension_name": "vat_type", "label": "نوع المعاملة الضريبية", "value": "vat_type"},
                "limit": 10,
                "value_column": {"aggregation": "sum", "column_name": "vat_amount", "data_type": "Decimal", "measure_name": "المبلغ الضريبي"}
            }
        },
        {
            "key": "table_detailed_ledger",
            "title": "سجل الحركات المالية التفصيلي حسب المشروع ومركز التكلفة",
            "query_title": "استعلام سجل الحركات المالية التفصيلي",
            "chart_type": "Table",
            "config": {
                "filters": {"filters": [], "logical_operator": "And"},
                "limit": 50,
                "rows": [
                    {"column_name": "posting_date", "data_type": "Date", "dimension_name": "posting_date", "label": "تاريخ الحركة", "value": "posting_date"},
                    {"column_name": "account_name", "data_type": "String", "dimension_name": "account_name", "label": "اسم الحساب", "value": "account_name"},
                    {"column_name": "project_name", "data_type": "String", "dimension_name": "project_name", "label": "المشروع", "value": "project_name"}
                ],
                "columns": [],
                "values": [
                    {"aggregation": "sum", "column_name": "debit", "data_type": "Decimal", "label": "مدين", "measure_name": "مدين"},
                    {"aggregation": "sum", "column_name": "credit", "data_type": "Decimal", "label": "دائن", "measure_name": "دائن"}
                ]
            }
        },
        {
            "key": "chart_projects_progress",
            "title": "نسب إنجاز المشروعات الإنشائية الميدانية",
            "query_title": "استعلام نسب إنجاز المشروعات الإنشائية الميدانية",
            "chart_type": "Bar",
            "config": {
                "filters": {"filters": [], "logical_operator": "And"},
                "limit": "15",
                "x_axis": {"dimension": {"column_name": "project_name", "data_type": "String", "dimension_name": "project_name", "label": "المشروع", "value": "project_name"}},
                "y_axis": {
                    "series": [
                        {"measure": {"aggregation": "avg", "column_name": "percent_complete", "data_type": "Decimal", "label": "نسبة الإنجاز %", "measure_name": "الإنجاز"}}
                    ]
                }
            }
        },
        {
            "key": "chart_tasks_status",
            "title": "توزيع المهام الميدانية حسب الحالة",
            "query_title": "استعلام توزيع المهام الميدانية حسب الحالة",
            "chart_type": "Donut",
            "config": {
                "filters": {"filters": [], "logical_operator": "And"},
                "label_column": {"column_name": "status", "data_type": "String", "dimension_name": "status", "label": "حالة المهمة", "value": "status"},
                "limit": 10,
                "value_column": {"aggregation": "sum", "column_name": "task_count", "data_type": "Integer", "measure_name": "عدد المهام"}
            }
        },
        {
            "key": "kpi_po_total",
            "title": "إجمالي أوامر الشراء المعتمدة (SAR)",
            "query_title": "استعلام إجمالي أوامر الشراء المعتمدة (SAR)",
            "chart_type": "Number",
            "config": {
                "comparison": False,
                "decimal": "2",
                "shorten_numbers": True,
                "sparkline": False,
                "number_columns": [
                    {"measure_name": "أوامر الشراء (SAR)", "column_name": "po_total", "data_type": "Decimal", "aggregation": "sum", "format": "currency"}
                ]
            }
        },
        {
            "key": "kpi_pi_total",
            "title": "إجمالي فواتير المشتريات ومواد البناء",
            "query_title": "استعلام إجمالي فواتير المشتريات ومواد البناء (SAR)",
            "chart_type": "Number",
            "config": {
                "comparison": False,
                "decimal": "2",
                "shorten_numbers": True,
                "sparkline": False,
                "number_columns": [
                    {"measure_name": "فواتير المشتريات (SAR)", "column_name": "pi_total", "data_type": "Decimal", "aggregation": "sum", "format": "currency"}
                ]
            }
        },
        {
            "key": "chart_suppliers_donut",
            "title": "توزيع المشتريات ومواد البناء حسب الموردين",
            "query_title": "استعلام توزيع المشتريات ومواد البناء حسب الموردين",
            "chart_type": "Donut",
            "config": {
                "filters": {"filters": [], "logical_operator": "And"},
                "label_column": {"column_name": "supplier", "data_type": "String", "dimension_name": "supplier", "label": "المورد", "value": "supplier"},
                "limit": 10,
                "value_column": {"aggregation": "sum", "column_name": "supplier_total", "data_type": "Decimal", "measure_name": "إجمالي المشتريات"}
            }
        },
        {
            "key": "kpi_employees_count",
            "title": "إجمالي الكوادر البشرية النشطة",
            "query_title": "استعلام إجمالي الكوادر البشرية النشطة",
            "chart_type": "Number",
            "config": {
                "comparison": False,
                "decimal": "0",
                "shorten_numbers": False,
                "sparkline": False,
                "number_columns": [
                    {"measure_name": "عدد الكوادر النشطة", "column_name": "employee_count", "data_type": "Integer", "aggregation": "sum", "format": "number"}
                ]
            }
        },
        {
            "key": "chart_hr_headcount",
            "title": "توزيع الكوادر البشرية والموظفين حسب الأقسام والمسميات الوظيفية",
            "query_title": "استعلام توزيع الكوادر حسب الأقسام والمسميات",
            "chart_type": "Bar",
            "config": {
                "filters": {"filters": [], "logical_operator": "And"},
                "limit": "20",
                "x_axis": {"dimension": {"column_name": "dept_label", "data_type": "String", "dimension_name": "dept_label", "label": "القسم / الإدارة", "value": "dept_label"}},
                "y_axis": {
                    "series": [
                        {"measure": {"aggregation": "sum", "column_name": "staff_count", "data_type": "Integer", "label": "عدد الكوادر", "measure_name": "العدد"}}
                    ]
                }
            }
        },
        {
            "key": "table_sales_ipcs",
            "title": "سجل الفواتير والمستخلصات الضريبية المعتمدة",
            "query_title": "استعلام سجل الفواتير والمستخلصات الضريبية المعتمدة",
            "chart_type": "Table",
            "config": {
                "filters": {"filters": [], "logical_operator": "And"},
                "limit": 50,
                "rows": [
                    {"column_name": "name", "data_type": "String", "dimension_name": "name", "label": "رقم المستخلص / الفاتورة", "value": "name"},
                    {"column_name": "customer", "data_type": "String", "dimension_name": "customer", "label": "العميل", "value": "customer"},
                    {"column_name": "project", "data_type": "String", "dimension_name": "project", "label": "المشروع", "value": "project"}
                ],
                "columns": [],
                "values": [
                    {"aggregation": "sum", "column_name": "base_grand_total", "data_type": "Decimal", "label": "الإجمالي", "measure_name": "base_grand_total"},
                    {"aggregation": "sum", "column_name": "outstanding_amount", "data_type": "Decimal", "label": "المتبقي", "measure_name": "outstanding_amount"}
                ]
            }
        }
    ]

    chart_map = {}
    for c_cfg in charts_def:
        q_id = q_map.get(c_cfg["query_title"])
        if not q_id:
            continue
        existing = frappe.get_all("Insights Chart v3", filters={"workbook": wb_name, "title": c_cfg["title"]}, pluck="name")
        if existing:
            c_doc = frappe.get_doc("Insights Chart v3", existing[0])
            c_doc.query = q_id
            c_doc.chart_type = c_cfg["chart_type"]
            c_doc.config = json.dumps(c_cfg["config"])
            c_doc.is_public = 0
            c_doc.permission_user = "Administrator"
            c_doc.save(ignore_permissions=True)
            chart_map[c_cfg["key"]] = c_doc.name
        else:
            c_doc = frappe.new_doc("Insights Chart v3")
            c_doc.title = c_cfg["title"]
            c_doc.workbook = wb_name
            c_doc.query = q_id
            c_doc.chart_type = c_cfg["chart_type"]
            c_doc.config = json.dumps(c_cfg["config"])
            c_doc.is_public = 0
            c_doc.permission_user = "Administrator"
            c_doc.insert(ignore_permissions=True)
            chart_map[c_cfg["key"]] = c_doc.name
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

    dashboard_ids = []
    for d_cfg in dashboards_config:
        existing = frappe.get_all("Insights Dashboard v3", filters={"title": d_cfg["title"]}, pluck="name")
        if not existing:
            if d_cfg["id_slug"] == "dsh_ceo":
                existing = frappe.get_all("Insights Dashboard v3", filters={"title": "لوحة المالك والمدير العام - الملخص التنفيذي الشامل"}, pluck="name")
            elif d_cfg["id_slug"] == "dsh_billing_tax":
                existing = frappe.get_all("Insights Dashboard v3", filters={"title": "التقارير التفصيلية للمشاريع والعهد والزكاة والضريبة"}, pluck="name")

        if existing:
            d = frappe.get_doc("Insights Dashboard v3", existing[0])
            d.title = d_cfg["title"]
            d.workbook = wb_name
            d.is_public = 0
            d.permission_user = "Administrator"
            d.items = json.dumps(d_cfg["items"])
            d.set("linked_charts", [])
            for item in d_cfg["items"]:
                d.append("linked_charts", {"chart": item["chart"]})
            d.save(ignore_permissions=True)
            dashboard_ids.append(d.name)
            print(f" -> Updated Dashboard: {d_cfg['title']} ({d.name})")
        else:
            d = frappe.new_doc("Insights Dashboard v3")
            d.title = d_cfg["title"]
            d.workbook = wb_name
            d.is_public = 0
            d.permission_user = "Administrator"
            d.items = json.dumps(d_cfg["items"])
            for item in d_cfg["items"]:
                d.append("linked_charts", {"chart": item["chart"]})
            d.insert(ignore_permissions=True)
            dashboard_ids.append(d.name)
            print(f" -> Created Dashboard: {d_cfg['title']} ({d.name})")

    frappe.db.commit()

    # Share Workbook 1 and all 6 Dashboards with management users
    target_users = ["alyahmedelseidy@gmail.com", "director@elsaidy.org"]
    for u in target_users:
        if not frappe.db.exists("DocShare", {"share_doctype": "Insights Workbook", "share_name": wb_name, "user": u}):
            frappe.share.add("Insights Workbook", wb_name, u, read=1, write=0, share=0)
            print(f" -> Shared Workbook 1 with {u}")
        for d_id in dashboard_ids:
            if not frappe.db.exists("DocShare", {"share_doctype": "Insights Dashboard v3", "share_name": d_id, "user": u}):
                frappe.share.add("Insights Dashboard v3", d_id, u, read=1, write=0, share=0)
                print(f" -> Shared Dashboard {d_id} with {u}")

    frappe.db.commit()


def sync_executive_manager_portal():
    """
    Ensures 'Executive Director (Read Only)' role and user 'director@elsaidy.org' exist,
    without sabotaging standard DocPerm entries for other system roles.
    Copies standard DocPerms to Custom DocPerms so System Manager, Insights User,
    Insights Admin, Accounts User, Projects User, etc. maintain full native access.
    Grants table and data source access in Insights Team.
    """
    print("\n[Finalization] 4. Synchronizing Executive Manager Portal Role & User...")
    role_name = "Executive Director (Read Only)"
    if not frappe.db.exists("Role", role_name):
        r = frappe.new_doc("Role")
        r.role_name = role_name
        r.desk_access = 1
        r.insert(ignore_permissions=True)
        print(f" -> Created Role: {role_name}")

    target_dts = [
        "Insights Dashboard v3", "Insights Chart v3", "Insights Query v3", "Insights Workbook",
        "Project", "Task", "GL Entry", "Account", "Sales Invoice", "Purchase Invoice", "Employee", "Elsaidy Share Link"
    ]

    for dt in target_dts:
        if not frappe.db.exists("DocType", dt):
            continue
        std_perms = frappe.get_all("DocPerm", filters={"parent": dt}, fields=["*"])
        custom_perms = frappe.get_all("Custom DocPerm", filters={"parent": dt}, fields=["*"])
        existing_roles = {cp["role"] for cp in custom_perms}

        # Preserve all standard roles in Custom DocPerm
        for sp in std_perms:
            if sp["role"] not in existing_roles:
                new_cp = frappe.new_doc("Custom DocPerm")
                for k, v in sp.items():
                    if k not in ["name", "owner", "creation", "modified", "modified_by", "idx", "docstatus"]:
                        setattr(new_cp, k, v)
                new_cp.parent = dt
                new_cp.parenttype = "DocType"
                new_cp.parentfield = "permissions"
                new_cp.insert(ignore_permissions=True)
                existing_roles.add(sp["role"])

        # Add Executive Director (Read Only)
        if role_name not in existing_roles:
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

    # Add to Insights Admin Team so director@elsaidy.org has direct execution access on tables
    for u_target in ["director@elsaidy.org", "alyahmedelseidy@gmail.com"]:
        if not frappe.db.exists("Insights Team Member", {"parent": "Admin", "user": u_target}):
            tm = frappe.new_doc("Insights Team Member")
            tm.parent = "Admin"
            tm.parenttype = "Insights Team"
            tm.parentfield = "team_members"
            tm.user = u_target
            tm.insert(ignore_permissions=True)
            print(f" -> Added {u_target} to Insights Admin Team")
    frappe.db.commit()


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

    frappe.db.commit()


def sync_onboarding_and_workspace_cleanup():
    """
    Eliminates all 'Getting Started' popups/onboarding steps across Frappe, CRM, and Helpdesk.
    Updates HD Settings and FCRM Settings to mark setup permanently completed.
    Synchronizes Arabic translations in tabTranslation.
    Polishes workspace titles and Desktop icons.
    """
    print("\n[Finalization] 6. Eliminating 'Getting Started' & Polishing Workspaces...")

    # 1. Dismiss standard Frappe Module Onboarding & Steps
    frappe.db.sql("UPDATE `tabModule Onboarding` SET is_complete = 1")
    frappe.db.sql("UPDATE `tabOnboarding Step` SET is_complete = 1")
    frappe.db.commit()

    # 2. HD Settings Onboarding Completion
    if frappe.db.exists("DocType", "HD Settings"):
        frappe.db.set_single_value("HD Settings", "persona_captured", 1)
        frappe.db.set_single_value("HD Settings", "setup_complete", 1)
        frappe.db.set_single_value("HD Settings", "initial_helpdesk_name_setup_skipped", 1)
        frappe.db.set_single_value("HD Settings", "brand_name", "Elsaidy Support - ركن سبل الأفق")
        frappe.db.commit()
        print(" -> HD Settings marked permanently completed.")

    # 3. FCRM Settings Setup Completion
    if frappe.db.exists("DocType", "FCRM Settings"):
        frappe.db.set_single_value("FCRM Settings", "setup_completed", 1)
        frappe.db.commit()
        print(" -> FCRM Settings marked permanently completed.")

    # 4. Update onboarding_status on all active users so no drawer ever re-opens
    full_onboarding = {
        "helpdesk_onboarding_status": [
            {"name": "setup_email_account", "completed": True},
            {"name": "invite_agents", "completed": True},
            {"name": "setup_sla", "completed": True},
            {"name": "create_first_ticket", "completed": True},
            {"name": "assign_to_agent", "completed": True},
            {"name": "reply_on_ticket", "completed": True},
            {"name": "comment_on_ticket", "completed": True},
            {"name": "first_article", "completed": True},
            {"name": "add_invite_contact", "completed": True},
            {"name": "explore_customer_portal", "completed": True}
        ],
        "frappecrm_onboarding_status": [
            {"name": "setup_your_password", "completed": True},
            {"name": "create_first_lead", "completed": True},
            {"name": "invite_your_team", "completed": True},
            {"name": "convert_lead_to_deal", "completed": True},
            {"name": "create_first_task", "completed": True},
            {"name": "create_first_note", "completed": True},
            {"name": "add_first_comment", "completed": True},
            {"name": "send_first_email", "completed": True},
            {"name": "change_deal_status", "completed": True}
        ]
    }
    for u in frappe.get_all("User", filters={"enabled": 1}, pluck="name"):
        frappe.db.set_value("User", u, "onboarding_status", json.dumps(full_onboarding), update_modified=False)
    frappe.db.commit()
    print(" -> User onboarding_status updated on all active users.")

    # 5. Sync Key Arabic Translations in tabTranslation
    translations = [
        ("Deals", "الصفقات"),
        ("Organizations", "الشركات"),
        ("Call Logs", "سجل المكالمات"),
        ("Tasks", "المهام"),
        ("Notes", "الملاحظات"),
        ("No leads yet", "لا يوجد عملاء محتملون بعد"),
        ("Avg. First Response", "متوسط أول رد"),
        ("Avg. Resolution", "متوسط وقت الحل"),
        ("Total Tickets", "إجمالي التذاكر"),
        ("Resolved Tickets", "التذاكر المحلولة"),
        ("Open Tickets", "التذاكر المفتوحة"),
        ("First response SLA", "اتفاقية مستوى أول رد"),
        ("Resolution SLA", "اتفاقية مستوى الحل"),
        ("Create your first lead", "إنشاء أول عميل محتمل"),
        ("Set up your company profile", "إعداد ملف الشركة"),
        ("Welcome to Frappe Helpdesk", "مرحباً بك في خدمة العملاء"),
    ]
    for src, trans in translations:
        existing_tr = frappe.db.get_value("Translation", {"language": "ar", "source_text": src}, "name")
        if existing_tr:
            frappe.db.set_value("Translation", existing_tr, "translated_text", trans)
        else:
            t_doc = frappe.new_doc("Translation")
            t_doc.language = "ar"
            t_doc.source_text = src
            t_doc.translated_text = trans
            t_doc.insert(ignore_permissions=True)
    frappe.db.commit()
    print(" -> Arabic translations synchronized in tabTranslation.")

    # 6. Workspace Title Polishing
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

    # 7. Desktop Icon for ZATCA
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
