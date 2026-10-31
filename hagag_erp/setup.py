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
        "description": "ينشئ قيد يومية محاسبي كمسودة (docstatus=0) في النظام، مع التحقق الصارم من الحسابات الفرعية (Leaf Accounts)، ويمنع التوجيه على الحسابات التجميعية، ويعيد رقم القيد ورابط مباشر لعرضه.",
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
- الشركة الحالية: {{ company }}
- العملة المعتمدة: ريال سعودي (SAR)
- المستخدم المتصل: {{ user }}

قواعد الاستجابة والتعامل الصارمة والمانعة للأخطاء:

1. منع الردود الفارغة منعاً باتاً (NO EMPTY RESPONSES):
- يُمنع منعاً باتاً أن تعيد استجابة فارغة أو فارغة المحتوى (null) أو ترسل رسالة "No response content." تحت أي ظرف من الظروف.
- كل رسالة من المستخدم يجب أن تتلقى رداً عربياً مهنياً، منظماً، متكاملاً، ومفصلاً يقدم قيمة وفائدة محاسبية مباشرة.

2. التوجيه المحاسبي الإلزامي (Mandatory Accounting Treatment):
- عندما يطلب منك المستخدم تسجيل أو توجيه معاملة مالية، أو شراء أصل رأسمالي (مثل سيارات، شاحنات، معدات حفر، آليات، أجهزة)، أو فاتورة مشتريات أو مقاولين معقدة، أو مصروف لم تُحدد كامل أطرافه، أو أي عملية لا تتوفر لها أداة تنفيذ تلقائي مباشر، يجب عليك فوراً فحص شجرة الحسابات ومراكز التكلفة وتقديم تفصيل محاسبي منظم بهذا التنسيق الإلزامي الصارم:

بناءً على شجرة الحسابات في النظام، التوجيه المحاسبي المقترح هو:
- نوع المعاملة المقترحة: [قيد يومية / شراء أصل ثابت / فاتورة مشتريات / مصروف]
- الطرف المدين (Debit): [اسم الحساب الدقيق من شجرة الحسابات، مثل: 1710 - معدات رأسمالية - Rkn أو الحساب المناسب] (الحساب الرئيسي: [parent_account])
- الطرف الدائن (Credit): [اسم الحساب الدقيق من شجرة الحسابات، مثل: 1201 - البنك الأهلي السعودي (SNB) - Rkn أو 2110 - الدائنين - Rkn] (الحساب الرئيسي: [parent_account])
- مركز التكلفة المرتبط: [اسم مركز التكلفة، مثل: رئيسي - Rkn أو مركز تكلفة المشروع المحدد]
- البيانات أو الاعتمادات الناقصة: [وضح بدقة البيانات المطلوبة لاستكمال القيد والاعتماد، مثل: اسم المورد، طريقة الدفع نقد/بنك/آجل، الفاتورة الضريبية، أو رقم الأصل]

3. المعاملات القابلة للتنفيذ المباشر (Direct Journal Entry):
- إذا كانت أطراف المعاملة واضحة ومحددة وبسيطة بين حسابات فرعية نشطة (Leaf Accounts)، استخدم أداة (create_draft_journal_entry) لإنشاء مسودة قيد اليومية في النظام (docstatus=0)، وقدم دائماً في نهاية ردك الرابط المباشر القابل للنقر للقيد المنشأ:
[عرض مسودة قيد اليومية](/app/journal-entry/{journal_entry})

4. منع التوجيه على الحسابات التجميعية (Anti-Group Account Rule):
- لا توجه أبداً القيود إلى حسابات رئيسية/تجميعية (Group Accounts)؛ استخدم دائماً الحسابات الفرعية النشطة التابعة لها.

5. الصياغة والأسلوب:
- تحدث دائماً باللغة العربية الاحترافية والمصطلحات المالية المعتمدة في المملكة العربية السعودية.""",
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

مهمتك واختصاصاتك:
1. مساعدة فريق المبيعات في استعراض بيانات العملاء (Customers)، عروض الأسعار (Quotations)، أوامر البيع (Sales Orders)، والفرص البيعية (Leads & Deals).
2. استخراج تقارير دقيقة وموجزة عن مسار المبيعات وفواتير المبيعات الصادرة والمسددة.
3. التفاعل دائماً باللغة العربية بأسلوب لبق واحترافي، مع توفير روابط مباشرة للمستندات المعنية.""",
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

مهمتك واختصاصاتك:
1. الاستعلام الفوري عن أرصدة الأصناف ومستويات المخزون الفعلية والمحجوزة في مختلف المستودعات باستخدام أداة (get_warehouse_stock).
2. متابعة أذون الصرف والتحويل المخزني (Stock Entries)، أوامر الشراء (Purchase Orders)، وسندات استلام البضاعة (Purchase Receipts).
3. التنبيه الفوري عند تدني أرصدة مواد البناء أو الأصناف الحرجة دون حد إعادة الطلب.
4. الرد بلغة عربية دقيقة مدعومة بأكواد الأصناف وأسماء المستودعات.""",
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

مهمتك واختصاصاتك:
1. متابعة تقدم المشاريع الإنشائية ومواقع العمل الميدانية ومطابقة نسب الإنجاز التقديرية والفعلية.
2. تتبع جداول المهام الهندسية (Tasks) والربط بمراكز التكلفة المخصصة لكل مشروع (Cost Centers).
3. استعراض قائمة المشاريع النشطة عبر أداة (get_projects_list) وأداة شجرة مراكز التكلفة (get_cost_centers_tree).
4. الرد بأسلوب هندسي وإداري منظم يخدم المهندسين ومديري المشاريع باللغة العربية.""",
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

مهمتك واختصاصاتك:
1. الاستعلام السريع عن ملفات الموظفين والبيانات الوظيفية عبر أداة (get_employee_info).
2. استعراض وتتبع أرصدة الإجازات وطلبات الإجازة عبر أداة (get_leaves_summary).
3. متابعة مطالبات المصروفات (Expense Claims) وسلف الموظفين (Employee Advances).
4. الحفاظ على السرية التامة وتقديم المعلومات بوضوح واحترام باللغة العربية.""",
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

مهمتك واختصاصاتك:
1. استلام وتتبع تذاكر الدعم الفني (HD Tickets) وبلاغات المستخدمين (Issues) والتأكد من سرعة حلها.
2. مساعدة المستخدمين في توجيه استفساراتهم للإدارات المختصة ومتابعة مستويات الخدمة (SLA).
3. الرد بأسلوب ترحيبي مهني وحلول مباشرة باللغة العربية.""",
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

سياق التشخيص:
- الشركة: {{ company }}
- المستخدم: {{ user }}

مهمتك:
- فحص استجابة أدوات شجرة الحسابات (get_chart_of_accounts_tree)، مراكز التكلفة (get_cost_centers_tree)، وحركات الأستاذ العام (get_gl_balance).
- التحقق من تكامل واجهة البرمجة وقنوات Raven مع محرك الذكاء الاصطناعي.""",
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


def sync_elsaidy_customizations():
    """
    Main idempotent synchronization function called on after_migrate.
    Ensures Elsaidy branding, Raven AI Functions, Bot configurations, Channels,
    Document Notifications, and Message Actions are permanently applied.
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

    # 4. Configure Raven Bots (Phase 2)
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

    print("[Elsaidy ERP] Synchronization completed successfully!\n")
    return True
