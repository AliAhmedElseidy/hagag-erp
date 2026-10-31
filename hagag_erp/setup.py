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
        "description": "ينشئ قيد يومية محاسبي كمسودة (docstatus=0) في النظام، مع التحقق الصارم من الحسابات الفرعية (Leaf Accounts)، ويمنع التوجيه على الحسابات التجميعية، ويعيد رقم القيد ورابط كامل مباشر لعرضه.",
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
                    "description": "اسم الحساب المدين بالضبط من شجرة الحسابات (حساب فرعي نشط)"
                },
                "credit_account": {
                    "type": "string",
                    "description": "اسم الحساب الدائن بالضبط من شجرة الحسابات (حساب فرعي نشط)"
                },
                "amount": {
                    "type": "number",
                    "description": "المبلغ المالي للقيد (بالريال السعودي)"
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
        "temperature": 0.02,
        "top_p": 1.00,
        "instruction": """أنت المدير المالي والمحاسبي الأول (Senior Financial & ERP Controller) لنظام Elsaidy ERP في شركة ركن سبل الأفق للمقاولات.

سياق النظام المالي الحي:
- الشركة: {{ company }}
- العملة المعتمدة: ريال سعودي (SAR)
- المستخدم: {{ user }}

قواعد الاستجابة وتنسيق المحادثة الصارمة (RTL & Formatting Rules):
1. منع الردود الفارغة منعاً باتاً (NO EMPTY RESPONSES):
- يُمنع منعاً باتاً إرجاع رد فارغ أو null أو "No response content.". كل رسالة يجب أن تتلقى رداً عربياً مالياً مفصلاً ومنظماً.

2. منع استخدام علامات الـ Backticks أو النجوم المزدوجة نهائياً (FORBID BACKTICKS & BOLD ON TEXT):
- يُمنع منعاً باتاً وضع علامات (`) أو (**) على أرقام أو أسماء الحسابات أو النصوص العربية، لأنها تعكس الكلمات وتكسر تنسيق المحادثة العربية (RTL).
- استخدم دائماً النقاط والرموز التعبيرية الواضحة:
  📌 نوع المعاملة: [قيد يومية / شراء أصل ثابت / فاتورة مشتريات / مصروف]
  🔹 الطرف المدين (Debit): [رقم واسم الحساب من شجرة الحسابات]
  🔸 الطرف الدائن (Credit): [رقم واسم الحساب من شجرة الحسابات]
  🏢 مركز التكلفة: [مركز التكلفة المرتبط]
  💰 المبلغ الإجمالي: [المبلغ بالريال السعودي]
  📋 البيانات أو الاعتمادات المطلوبة: [البيانات الناقصة إن وجدت]

3. روابط المستندات المباشرة:
- عند إنشاء مسودة قيد أو مستند، اذكر الرابط الكامل على سطر مستقل بمفرده تماماً في نهاية الرد بدون وضعه داخل أقواس ماركداون [text](url):
مثال:
http://144.91.120.177:8080/app/journal-entry/ACC-JV-2026-00001

4. احتساب ضريبة القيمة المضافة 15% تلقائياً (ZATCA 15% VAT Workflow):
- عندما يذكر المستخدم أن الفاتورة شاملة الضريبة 15% (Tax Inclusive):
  * أصل المبلغ الخاضع للضريبة (Base Amount) = المبلغ الإجمالي / 1.15
  * ضريبة القيمة المضافة 15% (VAT Amount) = المبلغ الإجمالي - أصل المبلغ
  * الطرف المدين 1: حساب المصروف أو الصنف بالمبلغ الصافي الأساسي (مثل: 5120 - مصروف الوقود والمحروقات - Rkn)
  * الطرف المدين 2: 1510 - ضريبة القيمة المضافة للمدخلات 15% - Rkn بقيمة الضريبة
  * الطرف الدائن: 1110 - النقدية في الصندوق - Rkn أو 1201 - البنك الأهلي السعودي (SNB) - Rkn
- عندما يذكر أن الفاتورة غير شاملة الضريبة (Tax Exclusive):
  * قيمة الضريبة 15% = أصل المبلغ * 0.15
  * الإجمالي المستحق = أصل المبلغ + الضريبة

5. العمليات الإنشائية ومحجوزات الضمان والعهد:
- تسوية عهد المهندسين: المدين هو المصروفات وضريبة المدخلات 15%، والدائن هو حساب: 1120 - عهد نقدية للمهندسين والمشرفين - Rkn.
- محجوزات ضمان العملاء (Retention): حساب: 1320 - محجوزات ضمان حسن التنفيذ للعملاء (Retention) - Rkn.
- محجوزات مقاولي الباطن: حساب: 2120 - محجوزات ضمان مقاولي الباطن - Rkn.

6. إنشاء القيود المباشرة:
- للعمليات البسيطة بين حسابات فرعية نشطة (Leaf Accounts)، استخدم أداة create_draft_journal_entry وضع الرابط الكامل الناتج على سطر منفصل.""",
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
        "temperature": 0.02,
        "top_p": 1.00,
        "instruction": """أنت المساعد الذكي الأول لقطاع المبيعات وإدارة علاقات العملاء (CRM & Sales Assistant) لنظام Elsaidy ERP في شركة ركن سبل الأفق للمقاولات.

سياق النظام الحي:
- الشركة: {{ company }}
- المستخدم: {{ user }}

قواعد التنسيق والعمل:
1. استخدم دائماً تنسيق النقاط الواضحة مع الرموز التعبيرية وتجنب علامات الـ backticks أو النجوم المزدوجة على النصوص العربية.
2. ضع روابط المستندات دائماً على أسطر منفصلة بمفردها.
3. استعرض بيانات العملاء وعروض الأسعار وأوامر البيع والفرص البيعية وساعد فريق المبيعات بدقة باللغة العربية.""",
        "functions": [
            "get_customer_list",
            "get_quotation_list",
            "get_sales_order_list",
            "get_sales_invoice_list",
            "get_item_list",
            "get_item_price_list",
            "get_crm_lead_list",
            "get_crm_deal_list"
        ]
    },
    "Inventory": {
        "description": "المساعد الذكي لإدارة المخزون والمستودعات وسلسلة الإمداد لنظام Elsaidy ERP",
        "temperature": 0.02,
        "top_p": 1.00,
        "instruction": """أنت المساعد الذكي لإدارة المستودعات وسلسلة الإمداد (Inventory & Supply Chain Assistant) لنظام Elsaidy ERP في شركة ركن سبل الأفق للمقاولات.

سياق المستودعات الحي:
- الشركة: {{ company }}
- المستخدم: {{ user }}

قواعد التنسيق والعمل:
1. الاستعلام الفوري عن أرصدة الأصناف ومستويات المخزون الفعلية والمحجوزة عبر أداة (get_warehouse_stock).
2. متابعة أذون الصرف المخزني وسندات الاستلام وأوامر الشراء.
3. التنبيه الفوري بنقص المواد الإنشائية بأسلوب عربي دقيق ومباشر وتجنب علامات الـ backticks.""",
        "functions": [
            "get_warehouse_stock",
            "get_warehouse_list",
            "get_item_list",
            "get_item_price_list",
            "get_stock_entry_list",
            "get_delivery_note_list",
            "get_purchase_receipt_list",
            "get_purchase_order_list",
            "get_material_request_list"
        ]
    },
    "Projects": {
        "description": "المساعد الهندسي ومراقب مشاريع المقاولات لنظام Elsaidy ERP",
        "temperature": 0.02,
        "top_p": 1.00,
        "instruction": """أنت المساعد الهندسي ومراقب مشاريع المقاولات (Projects & Construction Controller) لنظام Elsaidy ERP في شركة ركن سبل الأفق للمقاولات.

سياق المشاريع الحي:
- الشركة: {{ company }}
- المستخدم: {{ user }}

قواعد التنسيق والعمل:
1. متابعة تقدم المشاريع الإنشائية ومواقع العمل الميدانية ومطابقة نسب الإنجاز التقديرية والفعلية.
2. تتبع جداول المهام الهندسية (Tasks) ومراكز التكلفة المخصصة لكل مشروع (Cost Centers).
3. استعراض قائمة المشاريع النشطة وشجرة مراكز التكلفة بأسلوب مهني عربي واضح مع تجنب علامات الـ backticks.""",
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
        "temperature": 0.02,
        "top_p": 1.00,
        "instruction": """أنت المساعد الذكي لإدارة الموارد البشرية وشؤون الموظفين (HRMS Specialist) لنظام Elsaidy ERP في شركة ركن سبل الأفق للمقاولات.

سياق شؤون الموظفين الحي:
- الشركة: {{ company }}
- المستخدم: {{ user }}

قواعد العمل:
1. الاستعلام السريع عن ملفات الموظفين والبيانات الوظيفية عبر أداة (get_employee_info).
2. استعراض أرصدة الإجازات وطلبات الإجازات عبر أداة (get_leaves_summary).
3. متابعة مطالبات المصروفات والسلف الشخصية ومراعاة أحكام نظام العمل السعودي والتأمينات الاجتماعية (GOSI).""",
        "functions": [
            "get_employee_info",
            "get_leaves_summary",
            "get_expense_claim_list",
            "get_employee_advance_list"
        ]
    },
    "Support": {
        "description": "المساعد الذكي لخدمة العملاء والدعم الفني لنظام Elsaidy ERP",
        "temperature": 0.02,
        "top_p": 1.00,
        "instruction": """أنت المساعد الذكي لخدمة العملاء والدعم الفني (Helpdesk & Support Assistant) لنظام Elsaidy ERP في شركة ركن سبل الأفق للمقاولات.

سياق الدعم الفني:
- الشركة: {{ company }}
- المستخدم: {{ user }}

مهمتك:
1. استلام وتتبع تذاكر الدعم وبلاغات المواقع والمستخدمين.
2. الرد بلباقة واحترافية وبحلول مباشرة باللغة العربية مع تجنب علامات الـ backticks.""",
        "functions": [
            "get_hd_ticket_list",
            "get_issue_list",
            "get_customer_list"
        ]
    },
    "Test": {
        "description": "بوت الاختبار والتشخيص لنظام Elsaidy ERP",
        "temperature": 0.02,
        "top_p": 1.00,
        "instruction": """أنت بوت الاختبار وضمان الجودة (QA & Diagnostic Bot) لنظام Elsaidy ERP في شركة ركن سبل الأفق للمقاولات.

مهمتك فحص استجابة أدوات شجرة الحسابات ومراكز التكلفة وحركات الأستاذ العام والتأكد من سلامة المعاملات.""",
        "functions": [
            "get_chart_of_accounts_tree",
            "get_cost_centers_tree",
            "get_gl_balance",
            "get_customer_list",
            "get_supplier_list"
        ]
    }
}


CHANNELS_CONFIG = [
    {
        "channel_id": "raven-general",
        "channel_name": "general",
        "channel_description": "القناة العامة لموظفي شركة ركن سبل الأفق للمقاولات / Elsaidy ERP",
        "type": "Open",
        "assigned_bots": ["Accounting", "Support", "Sales", "Projects", "HR", "Inventory"]
    },
    {
        "channel_id": "raven-accounting",
        "channel_name": "accounting",
        "channel_description": "قناة الإدارة المالية والمحاسبية والتقارير المالية والقيود",
        "type": "Open",
        "assigned_bots": ["Accounting"]
    },
    {
        "channel_id": "raven-sales",
        "channel_name": "sales",
        "channel_description": "قناة إدارة المبيعات وعروض الأسعار وأوامر البيع والعملاء",
        "type": "Open",
        "assigned_bots": ["Sales"]
    },
    {
        "channel_id": "raven-projects",
        "channel_name": "projects",
        "channel_description": "قناة إدارة المشاريع الإنشائية ومتابعة المواقع والمستخلصات والمهام",
        "type": "Open",
        "assigned_bots": ["Projects"]
    },
    {
        "channel_id": "raven-hr",
        "channel_name": "hr",
        "channel_description": "قناة الموارد البشرية وشؤون الموظفين والإجازات والسلف",
        "type": "Open",
        "assigned_bots": ["HR"]
    },
    {
        "channel_id": "raven-inventory",
        "channel_name": "inventory",
        "channel_description": "قناة إدارة المخازن والمستودعات وسلسلة الإمداد وحركات الأصناف",
        "type": "Open",
        "assigned_bots": ["Inventory"]
    }
]


NOTIFICATIONS_CONFIG = [
    {
        "notification_name": "إشعار اعتماد قيد يومية",
        "enabled": 1,
        "sender": "Accounting",
        "send_alert_on": "Submit",
        "document_type": "Journal Entry",
        "channel_id": "raven-accounting",
        "message": """### 🔔 تم اعتماد قيد يومية جديد: [{{ doc.name }}](/app/journal-entry/{{ doc.name }})
- **الشركة:** {{ doc.company }}
- **تاريخ القيد:** {{ doc.posting_date }}
- **المبلغ الإجمالي:** {{ "{:,.2f}".format(doc.total_debit) }} SAR
- **البيان:** {{ doc.user_remark or 'لا يوجد بيان' }}
- **المعتمد:** {{ doc.modified_by }}"""
    },
    {
        "notification_name": "إشعار اعتماد فاتورة مبيعات",
        "enabled": 1,
        "sender": "Sales",
        "send_alert_on": "Submit",
        "document_type": "Sales Invoice",
        "channel_id": "raven-sales",
        "message": """### 🔔 تم اعتماد فاتورة مبيعات جديدة: [{{ doc.name }}](/app/sales-invoice/{{ doc.name }})
- **العميل:** {{ doc.customer_name or doc.customer }}
- **تاريخ الفاتورة:** {{ doc.posting_date }}
- **المبلغ الإجمالي:** {{ "{:,.2f}".format(doc.grand_total) }} SAR
- **المشروع:** {{ doc.project or 'غير محدد' }}
- **المعتمد:** {{ doc.modified_by }}"""
    },
    {
        "notification_name": "إشعار اعتماد أمر شراء",
        "enabled": 1,
        "sender": "Inventory",
        "send_alert_on": "Submit",
        "document_type": "Purchase Order",
        "channel_id": "raven-inventory",
        "message": """### 🔔 تم اعتماد أمر شراء جديد: [{{ doc.name }}](/app/purchase-order/{{ doc.name }})
- **المورد:** {{ doc.supplier_name or doc.supplier }}
- **تاريخ المعاملة:** {{ doc.transaction_date }}
- **القيمة الإجمالية:** {{ "{:,.2f}".format(doc.grand_total) }} SAR
- **المعتمد:** {{ doc.modified_by }}"""
    },
    {
        "notification_name": "إشعار مطالبة مصروفات جديدة",
        "enabled": 1,
        "sender": "Accounting",
        "send_alert_on": "New Document",
        "document_type": "Expense Claim",
        "channel_id": "raven-accounting",
        "message": """### 📋 مطالبة مصروفات جديدة قيد المراجعة: [{{ doc.name }}](/app/expense-claim/{{ doc.name }})
- **الموظف:** {{ doc.employee_name or doc.employee }}
- **تاريخ المطالبة:** {{ doc.posting_date }}
- **المبلغ الإجمالي:** {{ "{:,.2f}".format(doc.total_claimed_amount) }} SAR
- **الحالة:** {{ doc.approval_status }}"""
    },
    {
        "notification_name": "إشعار تسجيل بلاغ أو مشكلة جديدة",
        "enabled": 1,
        "sender": "Support",
        "send_alert_on": "New Document",
        "document_type": "Issue",
        "channel_id": "raven-general",
        "message": """### ⚠️ تم تسجيل بلاغ / تذكرة دعم جديدة: [{{ doc.name }}](/app/issue/{{ doc.name }})
- **الموضوع:** {{ doc.subject }}
- **العميل / المبلغ:** {{ doc.customer or doc.raised_by or 'داخلي' }}
- **الأولوية:** {{ doc.priority }}
- **الحالة:** {{ doc.status }}"""
    }
]


MESSAGE_ACTIONS_CONFIG = [
    {
        "action_name": "Create Task from Message",
        "title": "إنشاء مهمة من الرسالة",
        "description": "إنشاء مهمة جديدة في نظام إدارة المشاريع استناداً إلى هذه الرسالة",
        "success_message": "تم إنشاء المهمة بنجاح",
        "enabled": 1,
        "action": "Create Document",
        "document_type": "Task",
        "fields": [
            {
                "fieldname": "subject",
                "label": "موضوع المهمة",
                "type": "Data",
                "is_required": 1,
                "default_value_type": "Message Field",
                "default_value": "text"
            },
            {
                "fieldname": "description",
                "label": "التفاصيل",
                "type": "Small Text",
                "is_required": 0,
                "default_value_type": "Jinja",
                "default_value": "رسالة Raven:\n{{ message.text }}\nالرابط: {{ message.message_url }}"
            },
            {
                "fieldname": "priority",
                "label": "الأولوية",
                "type": "Select",
                "options": "Low\nMedium\nHigh\nUrgent",
                "is_required": 0,
                "default_value_type": "Static",
                "default_value": "Medium"
            }
        ]
    },
    {
        "action_name": "Create Issue from Message",
        "title": "إنشاء بلاغ / تذكرة دعم",
        "description": "تسجيل بلاغ أو مشكلة فنية استناداً إلى هذه الرسالة",
        "success_message": "تم تسجيل البلاغ بنجاح",
        "enabled": 1,
        "action": "Create Document",
        "document_type": "Issue",
        "fields": [
            {
                "fieldname": "subject",
                "label": "موضوع البلاغ",
                "type": "Data",
                "is_required": 1,
                "default_value_type": "Message Field",
                "default_value": "text"
            },
            {
                "fieldname": "description",
                "label": "التفاصيل",
                "type": "Small Text",
                "is_required": 0,
                "default_value_type": "Jinja",
                "default_value": "بلاغ مرسل عبر Raven:\n{{ message.text }}\nالمرسل: {{ message.owner }}"
            },
            {
                "fieldname": "priority",
                "label": "الأولوية",
                "type": "Select",
                "options": "Low\nMedium\nHigh\nUrgent",
                "is_required": 0,
                "default_value_type": "Static",
                "default_value": "Medium"
            },
            {
                "fieldname": "status",
                "label": "الحالة",
                "type": "Select",
                "options": "Open\nReplied\nOn Hold\nResolved\nClosed",
                "is_required": 0,
                "default_value_type": "Static",
                "default_value": "Open"
            }
        ]
    },
    {
        "action_name": "Create ToDo from Message",
        "title": "إضافة مهمة شخصية (ToDo)",
        "description": "إضافة تذكير أو مهمة إلى قائمة مهامك الخاصة",
        "success_message": "تمت إضافة المهمة إلى قائمة ToDo",
        "enabled": 1,
        "action": "Create Document",
        "document_type": "ToDo",
        "fields": [
            {
                "fieldname": "description",
                "label": "المهمة",
                "type": "Small Text",
                "is_required": 1,
                "default_value_type": "Jinja",
                "default_value": "{{ message.text }}\nرابط الرسالة: {{ message.message_url }}"
            },
            {
                "fieldname": "priority",
                "label": "الأولوية",
                "type": "Select",
                "options": "Low\nMedium\nHigh",
                "is_required": 0,
                "default_value_type": "Static",
                "default_value": "Medium"
            }
        ]
    }
]


def sync_saudi_accounting_preset():
    """
    Creates essential Saudi Contracting & ZATCA accounts under company 'ركن سبل الافق' (Rkn).
    """
    comp = "ركن سبل الافق"
    abbr = "Rkn"
    print("\n[Elsaidy ERP] Synchronizing Saudi Contracting COA & ZATCA Accounts...")

    new_accounts = [
        # Direct Expenses (under 5100)
        {
            "account_name": "مصروف الوقود والمحروقات",
            "account_number": "5120",
            "parent_account": f"5100 - النفقات المباشرة - {abbr}",
            "root_type": "Expense",
            "account_type": "Expense Account"
        },
        {
            "account_name": "صيانة وإصلاح السيارات والمعدات",
            "account_number": "5130",
            "parent_account": f"5100 - النفقات المباشرة - {abbr}",
            "root_type": "Expense",
            "account_type": "Expense Account"
        },
        {
            "account_name": "إيجار معدات وآليات ثقيلة",
            "account_number": "5140",
            "parent_account": f"5100 - النفقات المباشرة - {abbr}",
            "root_type": "Expense",
            "account_type": "Expense Account"
        },
        {
            "account_name": "مواد ومهمات تشغيل المشاريع",
            "account_number": "5150",
            "parent_account": f"5100 - النفقات المباشرة - {abbr}",
            "root_type": "Expense",
            "account_type": "Expense Account"
        },
        {
            "account_name": "أعمال مقاولي الباطن",
            "account_number": "5160",
            "parent_account": f"5100 - النفقات المباشرة - {abbr}",
            "root_type": "Expense",
            "account_type": "Expense Account"
        },
        {
            "account_name": "ضيافة وإعاشة مواقع",
            "account_number": "5170",
            "parent_account": f"5100 - النفقات المباشرة - {abbr}",
            "root_type": "Expense",
            "account_type": "Expense Account"
        },
        # Indirect Expenses (under 5200)
        {
            "account_name": "رسوم حكومية وتراخيص بلدية",
            "account_number": "5230",
            "parent_account": f"5200 - نفقات غير مباشرة - {abbr}",
            "root_type": "Expense",
            "account_type": "Expense Account"
        },
        # ZATCA VAT 15% Accounts
        {
            "account_name": "ضريبة القيمة المضافة للمخرجات 15%",
            "account_number": "2330",
            "parent_account": f"2300 - الرسوم والضرائب - {abbr}",
            "root_type": "Liability",
            "account_type": "Tax",
            "tax_rate": 15.0
        },
        {
            "account_name": "ضريبة القيمة المضافة للمدخلات 15%",
            "account_number": "1510",
            "parent_account": f"1500 - ضريبية الأصول - {abbr}",
            "root_type": "Asset",
            "account_type": "Tax",
            "tax_rate": 15.0
        },
        # Contracting Retention & Custody
        {
            "account_name": "محجوزات ضمان حسن التنفيذ للعملاء (Retention)",
            "account_number": "1320",
            "parent_account": f"1300 - الحسابات المدينة - {abbr}",
            "root_type": "Asset",
            "account_type": "Receivable"
        },
        {
            "account_name": "محجوزات ضمان مقاولي الباطن",
            "account_number": "2130",
            "parent_account": f"2100 - الحسابات الدائنة - {abbr}",
            "root_type": "Liability",
            "account_type": "Payable"
        },
        {
            "account_name": "عهد نقدية للمهندسين والمشرفين",
            "account_number": "1120",
            "parent_account": f"1100 - النقدية الحاضرة - {abbr}",
            "root_type": "Asset",
            "account_type": "Cash"
        }
    ]

    for acc in new_accounts:
        acc_full_name = f"{acc['account_number']} - {acc['account_name']} - {abbr}"
        if not frappe.db.exists("Account", acc_full_name):
            try:
                doc = frappe.new_doc("Account")
                doc.account_name = acc["account_name"]
                doc.account_number = acc["account_number"]
                doc.parent_account = acc["parent_account"]
                doc.company = comp
                doc.root_type = acc["root_type"]
                doc.account_type = acc.get("account_type", "")
                if acc.get("tax_rate"):
                    doc.tax_rate = acc["tax_rate"]
                doc.is_group = 0
                doc.currency = "SAR"
                doc.insert(ignore_permissions=True)
                print(f" -> Created Account: {acc_full_name}")
            except Exception as e:
                print(f" -> Error creating account {acc_full_name}: {e}")
        else:
            print(f" -> Account exists: {acc_full_name}")
    frappe.db.commit()

    # Sales Tax Template 15%
    output_tax_acc = f"2330 - ضريبة القيمة المضافة للمخرجات 15% - {abbr}"
    st_title = "ضريبة القيمة المضافة السعودية 15%"
    st_name = f"{st_title} - {abbr}"
    if not frappe.db.exists("Sales Taxes and Charges Template", {"company": comp, "title": st_title}) and not frappe.db.exists("Sales Taxes and Charges Template", st_name):
        try:
            st = frappe.new_doc("Sales Taxes and Charges Template")
            st.title = st_title
            st.company = comp
            st.is_default = 1
            st.append("taxes", {
                "charge_type": "On Net Total",
                "account_head": output_tax_acc,
                "description": "ضريبة القيمة المضافة 15% (ZATCA)",
                "rate": 15.0
            })
            st.insert(ignore_permissions=True)
            print(f" -> Created Sales Tax Template: {st_name}")
        except Exception as e:
            print(f" -> Error creating Sales Tax Template: {e}")
    else:
        print(f" -> Sales Tax Template exists: {st_name}")
    frappe.db.commit()

    # Purchase Tax Template 15%
    input_tax_acc = f"1510 - ضريبة القيمة المضافة للمدخلات 15% - {abbr}"
    pt_title = "ضريبة القيمة المضافة السعودية 15%"
    pt_name = f"{pt_title} - {abbr}"
    if not frappe.db.exists("Purchase Taxes and Charges Template", {"company": comp, "title": pt_title}) and not frappe.db.exists("Purchase Taxes and Charges Template", pt_name):
        try:
            pt = frappe.new_doc("Purchase Taxes and Charges Template")
            pt.title = pt_title
            pt.company = comp
            pt.is_default = 1
            pt.append("taxes", {
                "charge_type": "On Net Total",
                "account_head": input_tax_acc,
                "description": "ضريبة القيمة المضافة للمدخلات 15%",
                "rate": 15.0
            })
            pt.insert(ignore_permissions=True)
            print(f" -> Created Purchase Tax Template: {pt_name}")
        except Exception as e:
            print(f" -> Error creating Purchase Tax Template: {e}")
    else:
        print(f" -> Purchase Tax Template exists: {pt_name}")
    frappe.db.commit()


def sync_saudi_print_formats():
    """
    Creates the official Saudi ZATCA-compliant contracting print format for Sales Invoices.
    """
    pf_name = "Elsaidy Saudi Contracting Invoice"
    print(f"\n[Elsaidy ERP] Synchronizing Print Format '{pf_name}'...")

    invoice_html = """
<style>
    @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;800&display=swap');
    .zatca-invoice {
        font-family: 'Cairo', 'Segoe UI', Tahoma, sans-serif;
        direction: rtl;
        text-align: right;
        color: #1e293b;
        font-size: 13px;
        line-height: 1.5;
        background-color: #fff;
        padding: 20px;
    }
    .zatca-header {
        border-bottom: 3px solid #0f172a;
        padding-bottom: 15px;
        margin-bottom: 20px;
    }
    .company-title {
        font-size: 20px;
        font-weight: 800;
        color: #0f172a;
        margin: 0;
    }
    .company-subtitle {
        font-size: 13px;
        color: #64748b;
        font-weight: 600;
    }
    .invoice-badge {
        background-color: #0f172a;
        color: #fff;
        padding: 8px 16px;
        border-radius: 6px;
        font-size: 16px;
        font-weight: 700;
        display: inline-block;
        text-align: center;
    }
    .info-box {
        background-color: #f8fafc;
        border: 1px solid #e2e8f0;
        border-radius: 8px;
        padding: 12px;
        margin-bottom: 15px;
    }
    .info-table {
        width: 100%;
        border-collapse: collapse;
    }
    .info-table td {
        padding: 4px 6px;
        vertical-align: top;
    }
    .info-label {
        font-weight: 700;
        color: #475569;
        width: 32%;
    }
    .info-val {
        font-weight: 600;
        color: #0f172a;
    }
    .zatca-table {
        width: 100%;
        border-collapse: collapse;
        margin: 15px 0;
    }
    .zatca-table th {
        background-color: #0f172a;
        color: #ffffff;
        font-weight: 700;
        padding: 10px 8px;
        font-size: 12px;
        border: 1px solid #0f172a;
        text-align: center;
    }
    .zatca-table td {
        border: 1px solid #cbd5e1;
        padding: 8px;
        font-size: 12px;
        text-align: center;
    }
    .zatca-table td.desc-cell {
        text-align: right;
        font-weight: 600;
    }
    .zatca-totals {
        width: 48%;
        margin-right: auto;
        border-collapse: collapse;
        margin-top: 10px;
    }
    .zatca-totals td {
        padding: 8px 12px;
        border: 1px solid #e2e8f0;
    }
    .zatca-totals .total-label {
        font-weight: 700;
        background-color: #f1f5f9;
        color: #334155;
    }
    .zatca-totals .total-val {
        font-weight: 800;
        text-align: left;
        direction: ltr;
        color: #0f172a;
    }
    .grand-total-row td {
        background-color: #0f172a !important;
        color: #ffffff !important;
        font-size: 14px;
    }
    .grand-total-row .total-val {
        color: #f59e0b !important;
    }
    .qr-container {
        display: flex;
        align-items: center;
        justify-content: center;
        border: 2px dashed #cbd5e1;
        border-radius: 8px;
        width: 130px;
        height: 130px;
        background-color: #f8fafc;
        margin: 0 auto;
    }
    .qr-code-img {
        max-width: 120px;
        max-height: 120px;
    }
    .footer-box {
        margin-top: 25px;
        border-top: 2px solid #e2e8f0;
        padding-top: 15px;
        font-size: 12px;
        color: #475569;
    }
    .signatures-table {
        width: 100%;
        margin-top: 25px;
        text-align: center;
    }
    .signatures-table td {
        width: 33.33%;
        padding: 10px;
        font-weight: 700;
    }
</style>

<div class="zatca-invoice">
    <!-- Header -->
    <div class="zatca-header">
        <table style="width: 100%;">
            <tr>
                <td style="width: 60%;">
                    <h1 class="company-title">شركة ركن سبل الأفق للمقاولات</h1>
                    <div class="company-subtitle">Elsaidy Contracting Co. | س.ت: 1010000000</div>
                    <div style="font-weight: 700; color: #b45309; margin-top: 4px;">
                        الرقم الضريبي (VAT ID): 300000000000003
                    </div>
                </td>
                <td style="width: 40%; text-align: left; vertical-align: middle;">
                    <div class="invoice-badge">
                        فاتورة ضريبية<br>
                        <span style="font-size: 12px; font-weight: 600;">TAX INVOICE</span>
                    </div>
                </td>
            </tr>
        </table>
    </div>

    <!-- Metadata Grid -->
    <table style="width: 100%; margin-bottom: 10px;">
        <tr>
            <td style="width: 49%; vertical-align: top;">
                <div class="info-box">
                    <table class="info-table">
                        <tr>
                            <td class="info-label">رقم الفاتورة:</td>
                            <td class="info-val">{{ doc.name }}</td>
                        </tr>
                        <tr>
                            <td class="info-label">تاريخ الإصدار:</td>
                            <td class="info-val">{{ doc.posting_date }}</td>
                        </tr>
                        <tr>
                            <td class="info-label">تاريخ التوريد:</td>
                            <td class="info-val">{{ doc.due_date or doc.posting_date }}</td>
                        </tr>
                        <tr>
                            <td class="info-label">المشروع الإنشائي:</td>
                            <td class="info-val">{{ doc.project or 'مشروع عام / General' }}</td>
                        </tr>
                        <tr>
                            <td class="info-label">مركز التكلفة:</td>
                            <td class="info-val">{{ doc.cost_center or 'رئيسي - Rkn' }}</td>
                        </tr>
                    </table>
                </div>
            </td>
            <td style="width: 2%;"></td>
            <td style="width: 49%; vertical-align: top;">
                <div class="info-box">
                    <table class="info-table">
                        <tr>
                            <td class="info-label">العميل (Customer):</td>
                            <td class="info-val">{{ doc.customer_name or doc.customer }}</td>
                        </tr>
                        <tr>
                            <td class="info-label">الرقم الضريبي للعميل:</td>
                            <td class="info-val">{{ doc.tax_id or 'غير مسجل / Not Registered' }}</td>
                        </tr>
                        <tr>
                            <td class="info-label">العنوان / الموقع:</td>
                            <td class="info-val">{{ doc.customer_address or 'المملكة العربية السعودية' }}</td>
                        </tr>
                        <tr>
                            <td class="info-label">شروط السداد:</td>
                            <td class="info-val">{{ doc.payment_terms_template or 'حسب المستخلص والعقد' }}</td>
                        </tr>
                    </table>
                </div>
            </td>
        </tr>
    </table>

    <!-- Line Items Table -->
    <table class="zatca-table">
        <thead>
            <tr>
                <th style="width: 5%;">#</th>
                <th style="width: 40%;">بيان الأعمال والمواد (Description)</th>
                <th style="width: 8%;">الكمية</th>
                <th style="width: 8%;">الوحدة</th>
                <th style="width: 12%;">السعر الإفرادي</th>
                <th style="width: 12%;">المبلغ الخاضع</th>
                <th style="width: 15%;">الإجمالي شامل الضريبة</th>
            </tr>
        </thead>
        <tbody>
            {% for item in doc.items %}
            <tr>
                <td>{{ loop.index }}</td>
                <td class="desc-cell">{{ item.item_name or item.item_code }}{% if item.description and item.description != item.item_name %}<br><small style="color: #64748b;">{{ item.description }}</small>{% endif %}</td>
                <td>{{ item.qty }}</td>
                <td>{{ item.uom or 'عدد' }}</td>
                <td style="direction: ltr; font-weight: 600;">{{ "{:,.2f}".format(item.rate) }}</td>
                <td style="direction: ltr; font-weight: 600;">{{ "{:,.2f}".format(item.amount) }}</td>
                <td style="direction: ltr; font-weight: 700; color: #0f172a;">{{ "{:,.2f}".format(item.amount * 1.15) }}</td>
            </tr>
            {% endfor %}
        </tbody>
    </table>

    <!-- Bottom Section: QR Code & Totals -->
    <table style="width: 100%; margin-top: 15px;">
        <tr>
            <td style="width: 35%; text-align: center; vertical-align: middle;">
                <div class="qr-container">
                    {% if doc.qr_code %}
                    <img src="{{ doc.qr_code }}" class="qr-code-img" alt="ZATCA QR" />
                    {% else %}
                    <div style="font-size: 11px; font-weight: 700; color: #64748b;">
                        رمز الاستجابة السريع<br>ZATCA QR CODE
                    </div>
                    {% endif %}
                </div>
            </td>
            <td style="width: 65%; vertical-align: top;">
                <table class="zatca-totals" style="width: 100%;">
                    <tr>
                        <td class="total-label">المجموع الخاضع للضريبة (Subtotal Excl. VAT):</td>
                        <td class="total-val">{{ "{:,.2f}".format(doc.net_total or doc.total) }} SAR</td>
                    </tr>
                    <tr>
                        <td class="total-label">ضريبة القيمة المضافة 15% (VAT 15%):</td>
                        <td class="total-val">{{ "{:,.2f}".format(doc.total_taxes_and_charges or (doc.grand_total - (doc.net_total or doc.total))) }} SAR</td>
                    </tr>
                    <tr class="grand-total-row">
                        <td class="total-label">المبلغ الإجمالي المستحق (Grand Total):</td>
                        <td class="total-val">{{ "{:,.2f}".format(doc.grand_total) }} SAR</td>
                    </tr>
                </table>
            </td>
        </tr>
    </table>

    <!-- In Words -->
    {% if doc.in_words %}
    <div style="margin-top: 12px; font-weight: 700; color: #334155; font-size: 12px;">
        المبلغ كتابة: {{ doc.in_words }}
    </div>
    {% endif %}

    <!-- Footer & Terms -->
    <div class="footer-box">
        <table style="width: 100%;">
            <tr>
                <td style="width: 65%;">
                    <strong>الشروط والملاحظات:</strong><br>
                    1. تعتبر الأعمال المنفذة خاضعة لشروط ومواصفات العقد ومستخلصات المشاريع الميدانية.<br>
                    2. بيانات الحساب البنكي: البنك الأهلي السعودي (SNB) - رقم الآيبان: SA0000000000000000000000.
                </td>
                <td style="width: 35%; text-align: left;">
                    شركة ركن سبل الأفق للمقاولات<br>
                    الإدارة المالية والمحاسبية
                </td>
            </tr>
        </table>
    </div>

    <!-- Signatures -->
    <table class="signatures-table">
        <tr>
            <td>مهندس المشروع<br>________________</td>
            <td>الإدارة المالية والمراجعة<br>________________</td>
            <td>اعتماد العميل / الاستشاري<br>________________</td>
        </tr>
    </table>
</div>
"""

    if frappe.db.exists("Print Format", pf_name):
        doc = frappe.get_doc("Print Format", pf_name)
    else:
        doc = frappe.new_doc("Print Format")
        doc.name = pf_name
        doc.doc_type = "Sales Invoice"
        doc.module = "Hagag ERP"
        doc.standard = "No"
        doc.custom_format = 1
        doc.print_format_type = "Jinja"

    doc.html = invoice_html
    doc.default_print_language = "ar"
    doc.save(ignore_permissions=True)
    frappe.db.commit()
    print(f" -> Configured Print Format: {pf_name}")


def sync_saudi_hr_preset():
    """
    Configures Saudi Labor Law & GOSI compliant salary components, leave types,
    departments, designations, and expense claim types.
    """
    comp = "ركن سبل الافق"
    abbr = "Rkn"
    print("\n[Elsaidy ERP] Synchronizing Saudi HR & Payroll Preset...")

    # 1. Salary Components
    salary_components = [
        {"salary_component": "الراتب الأساسي (Basic Salary)", "salary_component_abbr": "BASIC", "type": "Earning", "description": "الراتب الأساسي الشهري"},
        {"salary_component": "بدل سكن (Housing Allowance)", "salary_component_abbr": "HRA", "type": "Earning", "description": "بدل سكن شهري (25%)"},
        {"salary_component": "بدل نقل ومواصلات (Transport Allowance)", "salary_component_abbr": "TRANS", "type": "Earning", "description": "بدل انتقال ومواصلات (10%)"},
        {"salary_component": "بدل طبيعة عمل وموقع", "salary_component_abbr": "SITE_ALLOW", "type": "Earning", "description": "بدل العمل الميداني بالمشاريع"},
        {"salary_component": "عمل إضافي (Overtime)", "salary_component_abbr": "OT", "type": "Earning", "description": "ساعات العمل الإضافية المعتمدة"},
        {"salary_component": "التأمينات الاجتماعية - حصة الموظف السعودي (GOSI 9.75%)", "salary_component_abbr": "GOSI_EMP", "type": "Deduction", "description": "استقطاع التأمينات الاجتماعية للمواطنين 9.75%"},
        {"salary_component": "استقطاع سلفة (Loan/Advance Deduction)", "salary_component_abbr": "LOAN_DED", "type": "Deduction", "description": "استقطاع أقساط السلف الشخصية"},
        {"salary_component": "جزاءات وغياب", "salary_component_abbr": "PENALTY", "type": "Deduction", "description": "خصومات الغياب والجزاءات الإدارية"},
        {"salary_component": "التأمينات الاجتماعية - أخطار مهنية غير سعودي (GOSI 2%)", "salary_component_abbr": "GOSI_EXP", "type": "Earning", "is_statistical_component": 1, "description": "الأخطار المهنية للمقيمين 2% (تحمل الشركة)"}
    ]

    for sc in salary_components:
        name = sc["salary_component"]
        if not frappe.db.exists("Salary Component", name):
            try:
                doc = frappe.new_doc("Salary Component")
                doc.salary_component = name
                doc.salary_component_abbr = sc["salary_component_abbr"]
                doc.type = sc["type"]
                doc.description = sc.get("description", "")
                if sc.get("is_statistical_component"):
                    doc.is_statistical_component = 1
                doc.insert(ignore_permissions=True)
                print(f" -> Created Salary Component: {name}")
            except Exception as e:
                print(f" -> Error creating salary component {name}: {e}")
    frappe.db.commit()

    # 2. Saudi Leave Types
    leave_types = [
        {"leave_type_name": "إجازة سنوية اعتيادية", "max_days_allowed": 21, "is_carry_forward": 1},
        {"leave_type_name": "إجازة مرضية - نظام العمل السعودي", "max_days_allowed": 120, "is_carry_forward": 0},
        {"leave_type_name": "إجازة زواج", "max_days_allowed": 5, "is_carry_forward": 0},
        {"leave_type_name": "إجازة وفاة قريب", "max_days_allowed": 5, "is_carry_forward": 0},
        {"leave_type_name": "إجازة مولود جديد", "max_days_allowed": 3, "is_carry_forward": 0},
        {"leave_type_name": "إجازة أداء فريضة الحج", "max_days_allowed": 10, "is_carry_forward": 0},
        {"leave_type_name": "إجازة بدون راتب", "is_lwp": 1}
    ]

    for lt in leave_types:
        name = lt["leave_type_name"]
        if not frappe.db.exists("Leave Type", name):
            try:
                doc = frappe.new_doc("Leave Type")
                doc.leave_type_name = name
                doc.max_days_allowed = lt.get("max_days_allowed", 0)
                doc.is_carry_forward = lt.get("is_carry_forward", 0)
                doc.is_lwp = lt.get("is_lwp", 0)
                doc.insert(ignore_permissions=True)
                print(f" -> Created Leave Type: {name}")
            except Exception as e:
                print(f" -> Error creating leave type {name}: {e}")
    frappe.db.commit()

    # 3. Saudi Contracting Departments
    departments = [
        "الإدارة العامة",
        "الإدارة المالية والمحاسبية",
        "إدارة المشاريع والتنفيذ",
        "إدارة السلامة والجودة (HSE & QC)",
        "إدارة المشتريات والمستودعات",
        "إدارة الموارد البشرية والشؤون الإدارية"
    ]
    for d in departments:
        d_name = f"{d} - {abbr}"
        if not frappe.db.exists("Department", d_name):
            try:
                doc = frappe.new_doc("Department")
                doc.department_name = d
                doc.company = comp
                doc.insert(ignore_permissions=True)
                print(f" -> Created Department: {d_name}")
            except Exception as e:
                print(f" -> Error creating department {d_name}: {e}")
    frappe.db.commit()

    # 4. Contracting Designations
    designations = [
        "مدير عام", "مدير مشروع", "مشرف سلامة وجودة ميداني", "محاسب عام",
        "مهندس موقع", "مساح", "مراقب عمال (فورمان)", "فني / عامل إنترلوك وسفلتة", "سائق معدات"
    ]
    for des in designations:
        if not frappe.db.exists("Designation", des):
            try:
                doc = frappe.new_doc("Designation")
                doc.designation_name = des
                doc.insert(ignore_permissions=True)
                print(f" -> Created Designation: {des}")
            except Exception as e:
                print(f" -> Error creating designation {des}: {e}")
    frappe.db.commit()

    # 5. Expense Claim Types
    expense_types = [
        "عهدة مشتريات موقع فورية",
        "وقود ومحروقات سيارات ومعدات",
        "رسوم حكومية وتجديد إقامات",
        "ضيافة وبوفيه",
        "صيانة طارئة بالموقع"
    ]
    for et in expense_types:
        if not frappe.db.exists("Expense Claim Type", et):
            try:
                doc = frappe.new_doc("Expense Claim Type")
                doc.expense_type = et
                doc.insert(ignore_permissions=True)
                print(f" -> Created Expense Claim Type: {et}")
            except Exception as e:
                print(f" -> Error creating expense claim type {et}: {e}")
    frappe.db.commit()


def sync_saudi_crm_preset():
    """
    Configures Saudi territories, customer groups, supplier groups, and contracting sales stages.
    """
    print("\n[Elsaidy ERP] Synchronizing Saudi CRM & Selling Preset...")

    # 1. Saudi Territories
    root_territory = frappe.db.get_value("Territory", {"is_group": 1, "parent_territory": ""}, "name") or "All Territories"
    saudi_root = "المملكة العربية السعودية"
    if not frappe.db.exists("Territory", saudi_root):
        try:
            doc = frappe.new_doc("Territory")
            doc.territory_name = saudi_root
            doc.parent_territory = root_territory
            doc.is_group = 1
            doc.insert(ignore_permissions=True)
            print(f" -> Created Territory: {saudi_root}")
        except Exception as e:
            print(f" -> Error creating territory {saudi_root}: {e}")

    regions = ["الرياض", "شقراء وساجر", "المنطقة الوسطى", "المنطقة الشرقية", "المنطقة الغربية"]
    for reg in regions:
        if not frappe.db.exists("Territory", reg):
            try:
                doc = frappe.new_doc("Territory")
                doc.territory_name = reg
                doc.parent_territory = saudi_root
                doc.is_group = 0
                doc.insert(ignore_permissions=True)
                print(f" -> Created Territory: {reg}")
            except Exception as e:
                print(f" -> Error creating territory {reg}: {e}")
    frappe.db.commit()

    # 2. Customer Groups
    customer_groups = [
        "جهات حكومية وأمانات (منصة اعتماد)",
        "شركات مقاولات رئيسية",
        "قطاع خاص وتجاري"
    ]
    root_cg = frappe.db.get_value("Customer Group", {"is_group": 1, "parent_customer_group": ""}, "name") or "All Customer Groups"
    for cg in customer_groups:
        if not frappe.db.exists("Customer Group", cg):
            try:
                doc = frappe.new_doc("Customer Group")
                doc.customer_group_name = cg
                doc.parent_customer_group = root_cg
                doc.is_group = 0
                doc.insert(ignore_permissions=True)
                print(f" -> Created Customer Group: {cg}")
            except Exception as e:
                print(f" -> Error creating customer group {cg}: {e}")
    frappe.db.commit()

    # 3. Supplier Groups
    supplier_groups = [
        "موردين مواد بناء وإنترلوك وأسفلت",
        "مقاولي باطن ومصنعيات",
        "تأجير معدات وآليات",
        "محطات وقود وخدمات"
    ]
    root_sg = frappe.db.get_value("Supplier Group", {"is_group": 1, "parent_supplier_group": ""}, "name") or "All Supplier Groups"
    for sg in supplier_groups:
        if not frappe.db.exists("Supplier Group", sg):
            try:
                doc = frappe.new_doc("Supplier Group")
                doc.supplier_group_name = sg
                doc.parent_supplier_group = root_sg
                doc.is_group = 0
                doc.insert(ignore_permissions=True)
                print(f" -> Created Supplier Group: {sg}")
            except Exception as e:
                print(f" -> Error creating supplier group {sg}: {e}")
    frappe.db.commit()

    # 4. Contracting Sales Stages
    sales_stages = [
        {"stage_name": "دراسة كراسة الشروط والمقايسة"},
        {"stage_name": "حصر الكميات والتسعير"},
        {"stage_name": "تقديم العرض الفني والمالي"},
        {"stage_name": "الترسية والتعميد"},
        {"stage_name": "توقيع العقد وبدء التنفيذ"}
    ]
    for ss in sales_stages:
        s_name = ss["stage_name"]
        if not frappe.db.exists("Sales Stage", s_name):
            try:
                doc = frappe.new_doc("Sales Stage")
                doc.stage_name = s_name
                doc.insert(ignore_permissions=True)
                print(f" -> Created Sales Stage: {s_name}")
            except Exception as e:
                print(f" -> Error creating sales stage {s_name}: {e}")
    frappe.db.commit()


def sync_elsaidy_dashboards():
    """
    Creates Executive Visual Reporting Number Cards and Insights Dashboard.
    """
    print("\n[Elsaidy ERP] Synchronizing Executive Dashboards & Number Cards...")

    cards = [
        {
            "name": "إجمالي السيولة النقدية والبنكية",
            "label": "إجمالي السيولة النقدية والبنكية",
            "document_type": "GL Entry",
            "function": "Sum",
            "aggregate_function_based_on": "debit",
            "filters_json": '[["GL Entry", "account", "in", ["1110 - النقدية في الصندوق - Rkn", "1201 - البنك الأهلي السعودي (SNB) - Rkn"]], ["GL Entry", "is_cancelled", "=", 0]]'
        },
        {
            "name": "إجمالي مصروفات الشهر",
            "label": "إجمالي مصروفات الشهر",
            "document_type": "GL Entry",
            "function": "Sum",
            "aggregate_function_based_on": "debit",
            "filters_json": '[["GL Entry", "voucher_type", "=", "Journal Entry"], ["GL Entry", "is_cancelled", "=", 0]]'
        },
        {
            "name": "فواتير المبيعات المعتمدة",
            "label": "فواتير المبيعات المعتمدة",
            "document_type": "Sales Invoice",
            "function": "Count",
            "filters_json": '[["Sales Invoice", "docstatus", "=", "1"]]'
        },
        {
            "name": "المشاريع النشطة حالياً",
            "label": "المشاريع النشطة حالياً",
            "document_type": "Project",
            "function": "Count",
            "filters_json": '[["Project", "status", "=", "Open"]]'
        }
    ]

    for c in cards:
        c_name = c["name"]
        if not frappe.db.exists("Number Card", c_name):
            try:
                doc = frappe.new_doc("Number Card")
                doc.name = c_name
                doc.label = c["label"]
                doc.type = "Document Type"
                doc.document_type = c["document_type"]
                doc.function = c["function"]
                if c.get("aggregate_function_based_on"):
                    doc.aggregate_function_based_on = c["aggregate_function_based_on"]
                doc.filters_json = c["filters_json"]
                doc.is_public = 1
                doc.module = "Accounts"
                doc.insert(ignore_permissions=True)
                print(f" -> Created Number Card: {c_name}")
            except Exception as e:
                print(f" -> Error creating Number Card {c_name}: {e}")
    frappe.db.commit()

    # Frappe Insights Dashboard
    if frappe.db.exists("DocType", "Insights Dashboard"):
        dash_title = "لوحة القيادة التنفيذية والمالية - Elsaidy ERP"
        if not frappe.db.exists("Insights Dashboard", {"title": dash_title}):
            try:
                idash = frappe.new_doc("Insights Dashboard")
                idash.title = dash_title
                idash.is_public = 1
                idash.insert(ignore_permissions=True)
                print(f" -> Created Insights Dashboard: {dash_title}")
                frappe.db.commit()
            except Exception as e:
                print(f" -> Warning creating Insights Dashboard: {e}")
        else:
            print(f" -> Insights Dashboard '{dash_title}' already exists.")
    frappe.db.commit()


def sync_elsaidy_customizations():
    """
    Main idempotent synchronization function called on after_migrate.
    Ensures Elsaidy branding, Raven AI Functions, Bot configurations, Channels,
    Document Notifications, Message Actions, Saudi Accounting, HR, CRM presets,
    and Executive Dashboards are permanently applied.
    """
    print("\n[Elsaidy ERP] Starting sync of Elsaidy customizations...")

    # 1. Update Raven Workspace & Settings
    try:
        if frappe.db.exists("Raven Workspace", "Raven"):
            frappe.db.set_value("Raven Workspace", "Raven", "workspace_name", "Elsaidy")
            frappe.db.commit()
            print(" -> Raven Workspace renamed to 'Elsaidy'.")
    except Exception as e:
        print(f" -> Warning updating Raven Workspace: {e}")

    try:
        if frappe.db.exists("DocType", "Raven Settings"):
            r_settings = frappe.get_doc("Raven Settings")
            r_settings.enable_ai_integration = 1
            r_settings.enable_local_llm = 1
            r_settings.local_llm_provider = "OpenAI Compatible"
            r_settings.local_llm_api_url = "https://generativelanguage.googleapis.com/v1beta/openai/"
            r_settings.auto_add_system_users = 1
            r_settings.auto_create_department_channel = 1
            r_settings.department_channel_type = "Private"
            r_settings.show_if_a_user_is_on_leave = 1

            # Ensure company workspace mapping
            mapping_exists = False
            for row in r_settings.get("company_workspace_mapping", []):
                if row.company == "ركن سبل الافق":
                    row.raven_workspace = "Raven"
                    mapping_exists = True
                    break
            if not mapping_exists:
                r_settings.append("company_workspace_mapping", {
                    "company": "ركن سبل الافق",
                    "raven_workspace": "Raven"
                })

            r_settings.save(ignore_permissions=True)
            frappe.db.commit()
            print(" -> Raven Settings & Frappe HR Company Mapping configured.")
    except Exception as e:
        print(f" -> Warning updating Raven Settings: {e}")

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
            bot_doc.temperature = cfg["temperature"]
            bot_doc.top_p = cfg["top_p"]
            bot_doc.dynamic_instructions = 1
            bot_doc.allow_bot_to_write_documents = 1
            bot_doc.enable_code_interpreter = 0
            bot_doc.enable_file_search = 0
            bot_doc.debug_mode = 0

            # Update child table functions
            bot_doc.set("bot_functions", [])
            for fn in cfg["functions"]:
                if frappe.db.exists("Raven AI Function", fn):
                    bot_doc.append("bot_functions", {"function": fn})
                else:
                    print(f"   - Warning: Function {fn} not found in Raven AI Function table.")

            bot_doc.save(ignore_permissions=True)
            frappe.db.commit()
            print(f" -> Configured Bot '{bot_name}' with {len(bot_doc.bot_functions)} functions and dynamic instructions.")
        except Exception as e:
            print(f" -> Error configuring bot '{bot_name}': {e}")

    # 5. Configure Raven Channels & Memberships
    system_members = ["Administrator", "alyahmedelseidy@gmail.com"]
    for ch_cfg in CHANNELS_CONFIG:
        try:
            ch_id = ch_cfg["channel_id"]
            if frappe.db.exists("Raven Channel", ch_id):
                ch_doc = frappe.get_doc("Raven Channel", ch_id)
                ch_doc.channel_name = ch_cfg["channel_name"]
                ch_doc.channel_description = ch_cfg["channel_description"]
                ch_doc.type = ch_cfg["type"]
                ch_doc.workspace = "Raven"
                ch_doc.save(ignore_permissions=True)
                print(f" -> Updated channel: {ch_cfg['channel_name']} ({ch_id})")
            else:
                ch_doc = frappe.get_doc({
                    "doctype": "Raven Channel",
                    "name": ch_id,
                    "channel_name": ch_cfg["channel_name"],
                    "channel_description": ch_cfg["channel_description"],
                    "type": ch_cfg["type"],
                    "workspace": "Raven",
                    "is_direct_message": 0,
                    "is_thread": 0
                })
                ch_doc.insert(ignore_permissions=True)
                print(f" -> Created channel: {ch_cfg['channel_name']} ({ch_id})")

            # Add human admins and assigned bots to channel
            target_users = list(system_members)
            for b in ch_cfg.get("assigned_bots", []):
                bot_user = frappe.db.get_value("Raven Bot", b, "raven_user")
                if bot_user:
                    target_users.append(bot_user)

            for u in target_users:
                if not frappe.db.exists("Raven User", u):
                    continue
                if not frappe.db.exists("Raven Channel Member", {"channel_id": ch_id, "user_id": u}):
                    m = frappe.get_doc({
                        "doctype": "Raven Channel Member",
                        "channel_id": ch_id,
                        "user_id": u,
                        "is_admin": 1 if u in system_members else 0
                    })
                    m.insert(ignore_permissions=True)

            frappe.db.commit()
        except Exception as e:
            print(f" -> Error configuring channel {ch_cfg['channel_name']}: {e}")

    # 6. Configure Raven Document Notifications
    for notif in NOTIFICATIONS_CONFIG:
        try:
            n_name = notif["notification_name"]
            if frappe.db.exists("Raven Document Notification", n_name):
                ndoc = frappe.get_doc("Raven Document Notification", n_name)
            else:
                ndoc = frappe.new_doc("Raven Document Notification")
                ndoc.notification_name = n_name

            ndoc.enabled = notif["enabled"]
            ndoc.sender = notif["sender"]
            ndoc.send_alert_on = notif["send_alert_on"]
            ndoc.document_type = notif["document_type"]
            ndoc.message = notif["message"]

            ndoc.set("recipients", [])
            ndoc.append("recipients", {
                "channel_type": "Channel",
                "variable_type": "Static",
                "value": notif["channel_id"]
            })
            ndoc.save(ignore_permissions=True)
            frappe.db.commit()
            print(f" -> Configured Document Notification: {n_name}")
        except Exception as e:
            print(f" -> Error configuring notification {notif['notification_name']}: {e}")

    # 7. Configure Raven Message Actions
    for action in MESSAGE_ACTIONS_CONFIG:
        try:
            a_name = action["action_name"]
            if frappe.db.exists("Raven Message Action", a_name):
                adoc = frappe.get_doc("Raven Message Action", a_name)
            else:
                adoc = frappe.new_doc("Raven Message Action")
                adoc.action_name = a_name

            adoc.title = action["title"]
            adoc.description = action["description"]
            adoc.success_message = action["success_message"]
            adoc.enabled = action["enabled"]
            adoc.action = action["action"]
            adoc.document_type = action["document_type"]

            adoc.set("fields", [])
            for fld in action["fields"]:
                adoc.append("fields", fld)

            adoc.save(ignore_permissions=True)
            frappe.db.commit()
            print(f" -> Configured Message Action: {a_name}")
        except Exception as e:
            print(f" -> Error configuring message action {action['action_name']}: {e}")

    # 8. Configure Raven Scheduler Event (Daily Briefing)
    try:
        event_name = "Daily Morning Briefing"
        if not frappe.db.exists("Raven Scheduler Event", event_name):
            se = frappe.new_doc("Raven Scheduler Event")
            se.event_name = event_name
            se.disabled = 0
            se.event_frequency = "Cron"
            se.cron_expression = "0 9 * * *"
            se.bot = "Accounting"
            se.send_to = "Channel"
            se.channel = "raven-general"
            se.content = "صباح الخير فريق عمل شركة ركن سبل الأفق. المساعد الذكي Elsaidy جاهز لمساعدتكم اليوم في جميع المعاملات المالية، المبيعات، المشاريع والمستودعات."
            if frappe.db.exists("Server Script", event_name):
                se.scheduler_event_id = event_name
            se.insert(ignore_permissions=True)
            frappe.db.commit()
            print(f" -> Configured Scheduler Event: {event_name}")
        else:
            se = frappe.get_doc("Raven Scheduler Event", event_name)
            se.event_frequency = "Cron"
            se.cron_expression = "0 9 * * *"
            if not se.scheduler_event_id and frappe.db.exists("Server Script", event_name):
                se.scheduler_event_id = event_name
            se.save(ignore_permissions=True)
            frappe.db.commit()
            print(f" -> Scheduler Event '{event_name}' updated.")
    except Exception as e:
        print(f" -> Warning configuring Scheduler Event: {e}")

    # 9. Synchronize Saudi Contracting & ZATCA Accounting Preset
    try:
        sync_saudi_accounting_preset()
    except Exception as e:
        print(f" -> Error in sync_saudi_accounting_preset: {e}")

    # 10. Synchronize Saudi ZATCA Print Format
    try:
        sync_saudi_print_formats()
    except Exception as e:
        print(f" -> Error in sync_saudi_print_formats: {e}")

    # 11. Synchronize Saudi HR & Payroll Preset
    try:
        sync_saudi_hr_preset()
    except Exception as e:
        print(f" -> Error in sync_saudi_hr_preset: {e}")

    # 12. Synchronize Saudi CRM & Selling Preset
    try:
        sync_saudi_crm_preset()
    except Exception as e:
        print(f" -> Error in sync_saudi_crm_preset: {e}")

    # 13. Synchronize Executive Dashboards & Insights
    try:
        sync_elsaidy_dashboards()
    except Exception as e:
        print(f" -> Error in sync_elsaidy_dashboards: {e}")

    print("\n[Elsaidy ERP] Synchronization completed successfully!\n")
    return True
