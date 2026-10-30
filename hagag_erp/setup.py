import json
import os
import frappe


CUSTOM_FUNCTIONS = [
    {
        "name": "get_chart_of_accounts_tree",
        "function_name": "get_chart_of_accounts_tree",
        "description": "يجلب شجرة الحسابات الحية كاملة للشركة، متضمنة أسماء الحسابات، الحسابات الرئيسية، نوع الحساب، وما إذا كان حساباً تجميعياً أو فرعياً، مع الأرصدة الحالية.",
        "type": "Custom Function",
        "function_path": "hagag_erp.ai_tools.get_chart_of_accounts_tree",
        "reference_doctype": "Account",
        "params": {
            "type": "object",
            "properties": {
                "company": {
                    "type": "string",
                    "description": "اسم الشركة (اختياري، الافتراضي شركة ركن سبل الأفق)"
                }
            }
        }
    },
    {
        "name": "get_cost_centers_tree",
        "function_name": "get_cost_centers_tree",
        "description": "يجلب شجرة مراكز التكلفة الحية للشركة من النظام لتحديد مركز التكلفة المناسب.",
        "type": "Custom Function",
        "function_path": "hagag_erp.ai_tools.get_cost_centers_tree",
        "reference_doctype": "Cost Center",
        "params": {
            "type": "object",
            "properties": {
                "company": {
                    "type": "string",
                    "description": "اسم الشركة (اختياري)"
                }
            }
        }
    },
    {
        "name": "get_projects_list",
        "function_name": "get_projects_list",
        "description": "يجلب قائمة المشاريع الإنشائية ومواقع العمل مع نسبة الإنجاز والعميل وحالة المشروع.",
        "type": "Custom Function",
        "function_path": "hagag_erp.ai_tools.get_projects_list",
        "reference_doctype": "Project",
        "params": {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "description": "حالة المشروع مثل Open أو Completed"
                },
                "company": {
                    "type": "string",
                    "description": "اسم الشركة"
                }
            }
        }
    },
    {
        "name": "get_gl_balance",
        "function_name": "get_gl_balance",
        "description": "يحسب الأرصدة الحية لحركات الأستاذ العام (GL Entry) من إجمالي المدين والدائن والرصيد الصافي مع إمكانية التصفية بالحساب أو مركز التكلفة أو المشروع أو الفترة الزمنية.",
        "type": "Custom Function",
        "function_path": "hagag_erp.ai_tools.get_gl_balance",
        "reference_doctype": "GL Entry",
        "params": {
            "type": "object",
            "properties": {
                "account": {
                    "type": "string",
                    "description": "اسم الحساب المحدد"
                },
                "cost_center": {
                    "type": "string",
                    "description": "مركز التكلفة"
                },
                "project": {
                    "type": "string",
                    "description": "اسم المشروع"
                },
                "from_date": {
                    "type": "string",
                    "description": "من تاريخ YYYY-MM-DD"
                },
                "to_date": {
                    "type": "string",
                    "description": "إلى تاريخ YYYY-MM-DD"
                },
                "company": {
                    "type": "string",
                    "description": "اسم الشركة"
                }
            }
        }
    },
    {
        "name": "create_draft_journal_entry",
        "function_name": "create_draft_journal_entry",
        "description": "ينشئ قيد يومية محاسبي كمسودة (docstatus=0) في النظام، مع تحديد الحساب المدين، الحساب الدائن، المبلغ، مركز التكلفة، والمشروع، ويعيد رقم القيد ورابط مباشر لعرضه.",
        "type": "Custom Function",
        "function_path": "hagag_erp.ai_tools.create_draft_journal_entry",
        "reference_doctype": "Journal Entry",
        "params": {
            "type": "object",
            "properties": {
                "posting_date": {
                    "type": "string",
                    "description": "تاريخ القيد YYYY-MM-DD (الافتراضي اليوم)"
                },
                "debit_account": {
                    "type": "string",
                    "description": "اسم الحساب المدين بالضبط من شجرة الحسابات"
                },
                "credit_account": {
                    "type": "string",
                    "description": "اسم الحساب الدائن بالضبط من شجرة الحسابات"
                },
                "amount": {
                    "type": "number",
                    "description": "المبلغ المالي للقيد"
                },
                "cost_center": {
                    "type": "string",
                    "description": "مركز التكلفة (اختياري، يحدد الافتراضي إن لم يُحدد)"
                },
                "project": {
                    "type": "string",
                    "description": "المشروع المرتبط (اختياري)"
                },
                "user_remark": {
                    "type": "string",
                    "description": "البيان أو الملاحظة الخاصة بالقيد"
                },
                "company": {
                    "type": "string",
                    "description": "اسم الشركة (اختياري)"
                }
            },
            "required": ["debit_account", "credit_account", "amount"]
        }
    },
    {
        "name": "get_employee_info",
        "function_name": "get_employee_info",
        "description": "يجلب بيانات الموظف من النظام مثل القسم، المسمى الوظيفي، الحالة، ورقم الجوال.",
        "type": "Custom Function",
        "function_path": "hagag_erp.ai_tools.get_employee_info",
        "reference_doctype": "Employee",
        "params": {
            "type": "object",
            "properties": {
                "employee": {
                    "type": "string",
                    "description": "معرف الموظف (كود الموظف)"
                },
                "search_term": {
                    "type": "string",
                    "description": "اسم الموظف أو جزء منه للبحث"
                }
            }
        }
    },
    {
        "name": "get_leaves_summary",
        "function_name": "get_leaves_summary",
        "description": "يجلب ملخص طلبات الإجازات وأيام الغياب للموظف من النظام.",
        "type": "Custom Function",
        "function_path": "hagag_erp.ai_tools.get_leaves_summary",
        "reference_doctype": "Leave Application",
        "params": {
            "type": "object",
            "properties": {
                "employee": {
                    "type": "string",
                    "description": "كود الموظف"
                },
                "status": {
                    "type": "string",
                    "description": "حالة الإجازة مثل Approved أو Open"
                }
            }
        }
    },
    {
        "name": "get_warehouse_stock",
        "function_name": "get_warehouse_stock",
        "description": "يجلب الكميات الفعلية المتوفرة والمحجوزة للأصناف في المستودعات من النظام.",
        "type": "Custom Function",
        "function_path": "hagag_erp.ai_tools.get_warehouse_stock",
        "reference_doctype": "Bin",
        "params": {
            "type": "object",
            "properties": {
                "item_code": {
                    "type": "string",
                    "description": "كود الصنف"
                },
                "warehouse": {
                    "type": "string",
                    "description": "المستودع"
                }
            }
        }
    }
]


BOT_CONFIGS = {
    "Accounting": {
        "description": "المدير المالي والمحاسبي الأول لنظام Elsaidy ERP",
        "instruction": """أنت المدير المالي والمحاسبي الأول (Senior Financial & ERP Controller) لنظام Elsaidy ERP في شركة ركن سبل الأفق للمقاولات.
مهمتك:
1. الإشراف على المعاملات المالية، مراقبة شجرة الحسابات، الأستاذ العام (GL Entry)، القيود اليومية، مراكز التكلفة، ومشاريع المقاولات.
2. عند توجيه أو تسجيل أي قيد أو مصروف أو معاملة مالية، يجب عليك دائماً فحص شجرة الحسابات الحية ومراكز التكلفة في النظام، والرد بدقة بهذا التنسيق الإلزامي الصارم:
بناءً على شجرة الحسابات في النظام، التوجيه المحاسبي هو:
- من ح/ (المدين): [Exact Account Name] (الحساب الرئيسي: [parent_account])
- إلى ح/ (الدائن): [Exact Account Name] (الحساب الرئيسي: [parent_account])
- مركز التكلفة: [Exact Cost Center]

3. استخدم أداة إنشاء مسودة قيد اليومية (create_draft_journal_entry) لإنشاء القيد بحالة مسودة (docstatus=0)، وقدم دائماً في نهاية ردك الرابط المباشر القابل للنقر للقيد المنشأ على النحو التالي:
[عرض مسودة قيد اليومية](/app/journal-entry/{journal_entry})
4. أجب دائماً باللغة العربية الاحترافية والمصطلحات المالية المعتمدة في المملكة العربية السعودية.""",
        "functions": [
            "get_chart_of_accounts_tree",
            "get_cost_centers_tree",
            "get_projects_list",
            "get_gl_balance",
            "create_draft_journal_entry",
            "get_journal_entry_list",
            "get_payment_entry_list",
            "get_sales_invoice_list",
            "get_purchase_invoice_list",
            "get_customer_list",
            "get_supplier_list",
            "get_employee_advance_list",
            "get_expense_claim_list"
        ]
    },
    "Sales": {
        "description": "المساعد الذكي لإدارة المبيعات وعلاقات العملاء لنظام Elsaidy ERP",
        "instruction": """أنت المساعد الذكي الأول لقطاع المبيعات وإدارة علاقات العملاء (CRM & Sales Assistant) لنظام Elsaidy ERP في شركة ركن سبل الأفق للمقاولات.
مهمتك:
1. مساعدة فريق المبيعات في تتبع العملاء، العروض التقديمية (Quotations)، أوامر البيع (Sales Orders)، والفرص البيعية (Leads & Deals).
2. استخراج تقارير دقيقة عن المبيعات والعملاء الأكثر نشاطاً ومتابعة مسار الصفقات (Sales Pipeline).
3. الرد دائماً بأسلوب احترافي راقٍ باللغة العربية.""",
        "functions": [
            "get_customer_list",
            "get_quotation_list",
            "get_sales_order_list",
            "get_crm_lead_list",
            "get_crm_deal_list"
        ]
    },
    "Inventory": {
        "description": "المساعد الذكي لإدارة المخزون والمستودعات وسلسلة الإمداد لنظام Elsaidy ERP",
        "instruction": """أنت المساعد الذكي لإدارة المستودعات وسلسلة الإمداد (Inventory & Supply Chain Assistant) لنظام Elsaidy ERP في شركة ركن سبل الأفق للمقاولات.
مهمتك:
1. مراقبة مستويات المخزون وحركات الأصناف في المستودعات (Warehouses & Bins).
2. متابعة أذون الصرف والإضافة (Stock Entries)، أوامر الشراء (Purchase Orders)، وطلبات المواد (Material Requests).
3. تنبيه الفريق بأي نقص في المواد الإنشائية ومستويات إعادة الطلب.
4. الرد دائماً باللغة العربية الدقيقة مع ذكر الكميات وأكواد الأصناف والمستودعات بدقة.""",
        "functions": [
            "get_item_list",
            "get_warehouse_list",
            "get_warehouse_stock",
            "get_stock_entry_list",
            "get_delivery_note_list",
            "get_purchase_receipt_list",
            "get_purchase_order_list",
            "get_material_request_list",
            "get_item_price_list"
        ]
    },
    "Projects": {
        "description": "المساعد الهندسي ومراقب مشاريع المقاولات لنظام Elsaidy ERP",
        "instruction": """أنت المساعد الهندسي ومراقب مشاريع المقاولات (Projects & Construction Controller) لنظام Elsaidy ERP في شركة ركن سبل الأفق للمقاولات.
مهمتك:
1. متابعة تقدم المشاريع الإنشائية، نسب الإنجاز، وجداول المهام (Tasks).
2. ربط العمليات بمراكز التكلفة المخصصة للمشاريع وتتبع الميزانيات التقديرية والفعلية.
3. تقديم تقارير دورية واضحة للإدارة الهندسية باللغة العربية.""",
        "functions": [
            "get_project_list",
            "get_projects_list",
            "get_task_list",
            "get_cost_center_list",
            "get_cost_centers_tree"
        ]
    },
    "HR": {
        "description": "المساعد الذكي للموارد البشرية وشؤون الموظفين لنظام Elsaidy ERP",
        "instruction": """أنت المساعد الذكي لإدارة الموارد البشرية وشؤون الموظفين (HRMS Specialist) لنظام Elsaidy ERP في شركة ركن سبل الأفق للمقاولات.
مهمتك:
1. مساعدة الإدارة والموظفين في الاستعلام عن بيانات الموظفين، أرصدة الإجازات، وتفاصيل الحضور والانصراف.
2. تتبع طلبات الإجازات (Leave Applications)، السلف (Employee Advances)، ومطالبات المصاريف (Expense Claims).
3. الحفاظ على سرية البيانات وتقديم المعلومات بوضوح واحترام باللغة العربية.""",
        "functions": [
            "get_employee_info",
            "get_leaves_summary",
            "get_expense_claim_list",
            "get_employee_advance_list"
        ]
    },
    "Support": {
        "description": "المساعد الذكي لخدمة العملاء والدعم الفني لنظام Elsaidy ERP",
        "instruction": """أنت المساعد الذكي لخدمة العملاء والدعم الفني (Helpdesk & Support Assistant) لنظام Elsaidy ERP في شركة ركن سبل الأفق للمقاولات.
مهمتك:
1. استلام وتتبع تذاكر الدعم الفني (HD Tickets) والمشكلات التقنية والتنسيق لحلها بسرعة.
2. توفير إرشادات واضحة وسريعة للمستخدمين والعملاء، ومتابعة مستوى الخدمة (SLA).
3. الرد بأسلوب ترحيبي مهني وحلول مباشرة باللغة العربية.""",
        "functions": [
            "get_hd_ticket_list",
            "get_issue_list",
            "get_customer_list"
        ]
    },
    "Test": {
        "description": "بوت الاختبار والتشخيص لنظام Elsaidy ERP",
        "instruction": """أنت بوت الاختبار وضمان الجودة (QA & Diagnostic Bot) لنظام Elsaidy ERP في شركة ركن سبل الأفق للمقاولات.
مهمتك مساعدة مسؤولي النظام والمطورين في فحص تكامل الذكاء الاصطناعي مع شجرة الحسابات، مراكز التكلفة، وسجلات الأستاذ العام، والتأكد من استجابة الوظائف المخصصة.""",
        "functions": [
            "get_chart_of_accounts_tree",
            "get_cost_centers_tree",
            "get_gl_balance",
            "get_customer_list",
            "get_supplier_list"
        ]
    }
}


def sync_elsaidy_customizations():
    """
    Main idempotent synchronization function called on after_migrate.
    Ensures Elsaidy branding, Raven AI Functions, Bot configurations, and patches
    are permanently applied.
    """
    print("\n[Elsaidy ERP] Starting sync of Elsaidy customizations...")

    # 1. Update Raven Workspace
    try:
        if frappe.db.exists("Raven Workspace", "Raven"):
            frappe.db.set_value("Raven Workspace", "Raven", "workspace_name", "Elsaidy")
            frappe.db.commit()
            print(" -> Raven Workspace renamed to 'Elsaidy'.")
    except Exception as e:
        print(f" -> Warning updating Raven Workspace: {e}")

    # 2. Update Website Settings branding
    try:
        ws_settings = frappe.get_doc("Website Settings")
        ws_settings.app_name = "Elsaidy ERP"
        ws_settings.save(ignore_permissions=True)
        frappe.db.commit()
        print(" -> Website Settings updated to 'Elsaidy ERP'.")
    except Exception as e:
        print(f" -> Warning updating Website Settings: {e}")

    # 3. Register or Update Raven AI Functions
    for func in CUSTOM_FUNCTIONS:
        try:
            fn_name = func["name"]
            params_json = json.dumps(func["params"], indent=2)
            fn_def = {
                "name": fn_name,
                "description": func["description"],
                "strict": False,
                "parameters": func["params"]
            }
            fn_def_json = json.dumps(fn_def, indent=2)

            if frappe.db.exists("Raven AI Function", fn_name):
                doc = frappe.get_doc("Raven AI Function", fn_name)
                doc.function_name = func["function_name"]
                doc.description = func["description"]
                doc.type = func["type"]
                doc.function_path = func["function_path"]
                doc.reference_doctype = func["reference_doctype"]
                doc.params = params_json
                doc.function_definition = fn_def_json
                doc.save(ignore_permissions=True)
                print(f" -> Updated Raven AI Function: {fn_name}")
            else:
                doc = frappe.get_doc({
                    "doctype": "Raven AI Function",
                    "function_name": func["function_name"],
                    "description": func["description"],
                    "type": func["type"],
                    "function_path": func["function_path"],
                    "reference_doctype": func["reference_doctype"],
                    "params": params_json,
                    "function_definition": fn_def_json
                })
                doc.insert(ignore_permissions=True)
                print(f" -> Created Raven AI Function: {fn_name}")
            frappe.db.commit()
        except Exception as e:
            print(f" -> Error creating/updating function {func['name']}: {e}")

    # 4. Configure Raven Bots
    for bot_name, cfg in BOT_CONFIGS.items():
        try:
            if not frappe.db.exists("Raven Bot", bot_name):
                print(f" -> Raven Bot '{bot_name}' not found, skipping.")
                continue

            bot_doc = frappe.get_doc("Raven Bot", bot_name)
            bot_doc.description = cfg["description"]
            bot_doc.instruction = cfg["instruction"]
            bot_doc.allow_bot_to_write_documents = 1

            # Update child table functions
            bot_doc.set("bot_functions", [])
            for fn in cfg["functions"]:
                if frappe.db.exists("Raven AI Function", fn):
                    bot_doc.append("bot_functions", {"function": fn})
                else:
                    print(f"   - Warning: Function {fn} not found in Raven AI Function table.")

            bot_doc.save(ignore_permissions=True)
            frappe.db.commit()
            print(f" -> Configured Bot '{bot_name}' with {len(bot_doc.bot_functions)} functions.")
        except Exception as e:
            print(f" -> Error configuring bot '{bot_name}': {e}")

    # 5. Verify Raven Gemini patch
    try:
        patch_path = "/home/frappe/frappe-bench/apps/raven/raven/ai/agents_integration.py"
        if os.path.exists(patch_path):
            with open(patch_path, "r", encoding="utf-8") as f:
                content = f.read()
            if "model_dump(exclude_none=True)" not in content:
                print(" -> Applying exclude_none=True patch to Raven agents_integration.py...")
                content = content.replace("model_dump()", "model_dump(exclude_none=True)")
                with open(patch_path, "w", encoding="utf-8") as f:
                    f.write(content)
                print(" -> Raven Gemini patch verified and written.")
            else:
                print(" -> Raven Gemini exclude_none=True patch is already active.")
    except Exception as e:
        print(f" -> Warning verifying Gemini patch: {e}")

    print("[Elsaidy ERP] Synchronization completed successfully!\n")
    return True
