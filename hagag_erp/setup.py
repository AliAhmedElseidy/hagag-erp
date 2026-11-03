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
                },
                "amount_basis": {
                    "type": "string",
                    "description": "نوع المبلغ: inclusive (شامل الضريبة 15%) أو exclusive (غير شامل، تضاف الضريبة)"
                },
                "usage_type": {
                    "type": "string",
                    "description": "نوع الاستخدام: commercial_equipment (معدات موقع وآليات)، restricted_vehicle (سيارة خاصة مقيدة)، general_expense (مصروف عام)"
                },
                "has_valid_tax_invoice": {
                    "type": "boolean",
                    "description": "هل تتوفر فاتورة ضريبية نظامية مستوفية لاشتراطات هيئة الزكاة والضريبة والجمارك"
                },
                "tax_treatment_policy": {
                    "type": "string",
                    "description": "معالجة الضريبة غير المستردة: capitalize_to_expense (إضافتها للمصروف) أو expense_account (حساب 5235)"
                },
                "operation_id": {
                    "type": "string",
                    "description": "معرف العملية الموحد لمنع التكرار (Idempotency Key)"
                }
            },
            "required": ["debit_account", "credit_account", "amount"]
        }
    },
    {
        "name": "create_contractor_purchase_invoice",
        "function_name": "create_contractor_purchase_invoice",
        "description": "ينشئ فاتورة مشتريات أو مقاولي باطن كمسودة (docstatus=0) في النظام مرتبطة بقالب ضريبة المشتريات 15% لتظهر في سجل المشتريات وإقرار ZATCA، مع تأمين كامل ضد التكرار (Idempotency).",
        "type": "Custom Function",
        "function_path": "hagag_erp.ai_tools.create_contractor_purchase_invoice",
        "reference_doctype": "Purchase Invoice",
        "params": {
            "type": "object",
            "properties": {
                "supplier": {
                    "type": "string",
                    "description": "اسم المورد أو مقاول الباطن بالضبط"
                },
                "amount": {
                    "type": "number",
                    "description": "قيمة الفاتورة المالية (بالريال السعودي)"
                },
                "bill_no": {
                    "type": "string",
                    "description": "رقم فاتورة المورد الضريبية"
                },
                "bill_date": {
                    "type": "string",
                    "description": "تاريخ فاتورة المورد YYYY-MM-DD"
                },
                "posting_date": {
                    "type": "string",
                    "description": "تاريخ القيد والتسجيل المحاسبي YYYY-MM-DD"
                },
                "expense_account": {
                    "type": "string",
                    "description": "حساب المصروف أو تكلفة المشروع (مثل 5150 مواد أو 5160 مقاولي باطن)"
                },
                "item_name": {
                    "type": "string",
                    "description": "بيان أو وصف البند / الخدمة / التوريد"
                },
                "cost_center": {
                    "type": "string",
                    "description": "مركز التكلفة"
                },
                "project": {
                    "type": "string",
                    "description": "اسم المشروع المرتبط"
                },
                "amount_basis": {
                    "type": "string",
                    "description": "نوع المبلغ: inclusive (شامل الضريبة 15%) أو exclusive (غير شامل)"
                },
                "has_valid_tax_invoice": {
                    "type": "boolean",
                    "description": "هل تتوفر فاتورة ضريبية نظامية مستوفية لاشتراطات هيئة الزكاة"
                },
                "contract_type": {
                    "type": "string",
                    "description": "نوع العقد: عقد تجاري خاص أو عقد حكومي منصة اعتماد"
                },
                "operation_id": {
                    "type": "string",
                    "description": "معرف العملية الموحد لمنع التكرار (Idempotency Key)"
                },
                "company": {
                    "type": "string",
                    "description": "اسم الشركة (اختياري)"
                }
            },
            "required": ["supplier", "amount"]
        }
    },
    {
        "name": "create_custody_settlement_entry",
        "function_name": "create_custody_settlement_entry",
        "description": "ينشئ قيد تسوية عهدة موقع ميداني متعدد البنود مع احتساب وفصل ضريبة القيمة المضافة 15% تلقائياً وتوجيه المصروفات على حسابات المقاولات والعهد ويعيد رابط كامل مباشر للقيد.",
        "type": "Custom Function",
        "function_path": "hagag_erp.ai_tools.create_custody_settlement_entry",
        "reference_doctype": "Journal Entry",
        "params": {
            "type": "object",
            "properties": {
                "lines": {
                    "type": "array",
                    "description": "قائمة بنود المصروفات (الوصف، المبلغ، هل خاضع للضريبة، الحساب)"
                },
                "custody_account": {
                    "type": "string",
                    "description": "حساب العهدة الدائن (الافتراضي 1120 - عهد نقدية للمهندسين والمشرفين - Rkn)"
                },
                "project": {
                    "type": "string",
                    "description": "اسم المشروع المرتبط"
                },
                "cost_center": {
                    "type": "string",
                    "description": "مركز التكلفة"
                },
                "user_remark": {
                    "type": "string",
                    "description": "بيان تسوية العهدة"
                }
            }
        }
    },
    {
        "name": "get_project_financial_summary",
        "function_name": "get_project_financial_summary",
        "description": "يعرض ملخصاً مالياً وتنفيذياً لحظياً للمشروع أو للشركة ككل: السيولة النقدية والمصرفية، الإيرادات، التكاليف المباشرة، محجوزات الضمان، وصافي الموقف الضريبي لـ ZATCA.",
        "type": "Custom Function",
        "function_path": "hagag_erp.ai_tools.get_project_financial_summary",
        "reference_doctype": "Project",
        "params": {
            "type": "object",
            "properties": {
                "project": {
                    "type": "string",
                    "description": "اسم المشروع (اختياري، إن لم يُحدد يعرض ملخص عمليات الشركة ككل)"
                },
                "company": {
                    "type": "string",
                    "description": "اسم الشركة (اختياري)"
                }
            }
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
                    "description": "حالة الطلب مثل Approved أو Open"
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
    },
    {
        "name": "get_employee_custody_report",
        "function_name": "get_employee_custody_report",
        "description": "يجلب تقرير كشف تسوية ومطابقة العهد والسلف الشهرية للموظف، مع الفصل الصارم بين الأرصدة المقيدة بالدفاتر (GL Entry) والمسودات غير المرحلة، والفصل التام بين عهد المواقع والسلف الشخصية.",
        "type": "Custom Function",
        "function_path": "hagag_erp.ai_tools.get_employee_custody_report",
        "reference_doctype": "Employee",
        "params": {
            "type": "object",
            "properties": {
                "employee": {
                    "type": "string",
                    "description": "اسم الموظف أو رقمه الوظيفي (اختياري، الافتراضي موظف الجلسة)"
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
        "name": "simulate_employee_custody_workflow",
        "function_name": "simulate_employee_custody_workflow",
        "description": "محاكي العمليات المالية (Dry Run) لمعاينة أي عملية عهدة، مصروف، أو سلفة راتب قبل إنشائها، مع توضيح القيود والحسابات والأثر المالي دون حفظ أي بيانات.",
        "type": "Custom Function",
        "function_path": "hagag_erp.ai_tools.simulate_employee_custody_workflow",
        "reference_doctype": "Journal Entry",
        "params": {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "نص المعاملة باللغة العربية"
                },
                "sender_phone": {
                    "type": "string",
                    "description": "رقم هاتف المرسل للتحقق من هوية الموظف"
                },
                "company": {
                    "type": "string",
                    "description": "اسم الشركة"
                }
            },
            "required": ["text"]
        }
    },
    {
        "name": "record_employee_custody_expense",
        "function_name": "record_employee_custody_expense",
        "description": "ينشئ مسودة قيد يومية متوازن لتسوية مصروف مدفوع من عهدة موظف، مع احتساب ضريبة القيمة المضافة ZATCA 15% وحساب العهد النقدية 1120 كطرف دائن بدون فرض طرف موظف على حساب النقد.",
        "type": "Custom Function",
        "function_path": "hagag_erp.ai_tools.record_employee_custody_expense",
        "reference_doctype": "Journal Entry",
        "params": {
            "type": "object",
            "properties": {
                "employee": {
                    "type": "string",
                    "description": "اسم الموظف أو الرقم الوظيفي"
                },
                "amount": {
                    "type": "number",
                    "description": "مبلغ المصروف الإجمالي"
                },
                "expense_category": {
                    "type": "string",
                    "description": "تصنيف المصروف: fuel (وقود), maintenance (صيانة), project_materials (مواد ومهمات), etc."
                },
                "description": {
                    "type": "string",
                    "description": "شرح البند أو الفاتورة"
                },
                "is_inclusive": {
                    "type": "integer",
                    "description": "1 إذا كان المبلغ شاملاً الضريبة 15%، 0 إذا كان غير شامل"
                },
                "vehicle_type": {
                    "type": "string",
                    "description": "commercial_equipment (معدة موقع/مولد) أو passenger_restricted (سيارة ركوب)"
                }
            },
            "required": ["amount"]
        }
    },
    {
        "name": "record_salary_advance_deduction",
        "function_name": "record_salary_advance_deduction",
        "description": "ينشئ مسودة استقطاع سلفة راتب (Additional Salary) في نظام HRMS لخصمها من مسير الرواتب القادم للموظف، مع منع التكرار والفصل عن عهد المواقع.",
        "type": "Custom Function",
        "function_path": "hagag_erp.ai_tools.record_salary_advance_deduction",
        "reference_doctype": "Additional Salary",
        "params": {
            "type": "object",
            "properties": {
                "employee": {
                    "type": "string",
                    "description": "اسم الموظف أو رقمه الوظيفي"
                },
                "amount": {
                    "type": "number",
                    "description": "مبلغ السلفة الشخصية المراد خصمها"
                },
                "payroll_date": {
                    "type": "string",
                    "description": "تاريخ استحقاق الراتب YYYY-MM-DD"
                },
                "user_remark": {
                    "type": "string",
                    "description": "بيان السلفة"
                }
            },
            "required": ["employee", "amount"]
        }
    },
    {
        "name": "inspect_and_propose_jv_correction",
        "function_name": "inspect_and_propose_jv_correction",
        "description": "يفحص قيد اليومية ACC-JV-2026-00005 في حالته كمسودة ويقدم المقارنة المحاسبية لتصحيح الضريبة والعهد دون المساس بالدفاتر إلا بعد الموافقة.",
        "type": "Custom Function",
        "function_path": "hagag_erp.ai_tools.inspect_and_propose_jv_correction",
        "reference_doctype": "Journal Entry",
        "params": {
            "type": "object",
            "properties": {
                "company": {
                    "type": "string",
                    "description": "اسم الشركة"
                },
                "apply": {
                    "type": "integer",
                    "description": "0 للمعاينة فقط، 1 لتطبيق التعديل على المسودة"
                },
                "strategy": {
                    "type": "string",
                    "description": "pending_review (ضريبة معلقة 1520) أو commercial (ضريبة مستردة 1510)"
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
- يُمنع منعاً باتاً وضع علامات (`) أو (**) على أرقام أو أسماء الحسابات أو النصوص العربية، لأنها تسبب انعكاس اتجاه النص (RTL) وتشويه التنسيق.
- استخدم بدلاً منها النقاط المنظمة والرموز التعبيرية الواضحة:
  📌 رقم القيد:
  💰 المبلغ:
  🔹 الطرف المدين:
  🔸 الطرف الدائن:
  🏢 مركز التكلفة:

3. روابط المستندات المباشرة:
- عند إنشاء مسودة قيد أو مستند، اذكر الرابط الكامل على سطر مستقل بمفرده تماماً في نهاية الرد بدون وضعه داخل أقواس ماركداون [text](url):
مثال:
https://erp.elsaidy.org/app/journal-entry/ACC-JV-2026-00001

4. احتساب ضريبة القيمة المضافة 15% تلقائياً (ZATCA 15% VAT Workflow):
- عندما يذكر المستخدم أن الفاتورة شاملة الضريبة 15% (Tax Inclusive):
  * أصل المبلغ الخاضع للضريبة (Base Amount) = المبلغ الإجمالي / 1.15
  * ضريبة القيمة المضافة 15% (VAT Amount) = المبلغ الإجمالي - أصل المبلغ
  * الطرف المدين 1: حساب المصروف الصافي (مثل: 5120 - مصروف الوقود والمحروقات - Rkn)
  * الطرف المدين 2: 1510 - ضريبة القيمة المضافة للمدخلات 15% - Rkn أو 1520 قيد المراجعة
  * الطرف الدائن: 1110 - النقدية في الصندوق - Rkn أو 1120 - عهد نقدية للمهندسين والمشرفين - Rkn

5. تسوية العهد الميدانية (Site Custody Settlements):
- عند طلب تسوية عهدة موقع أو مهندس، استخدم create_custody_settlement_entry أو record_employee_custody_expense لإنشاء قيد اليومية كمسودة مع التحقق من الحسابات وتوزيع الضرائب وتصفية العهدة بدقة.
- حساب العهد النقدية 1120 هو حساب نقدية (Cash)، ولا يجوز محاسبياً أو في نظام ERPNext v16 وضع طرف موظف (Party) عليه.

6. الفصل التام بين عهد المواقع والسلف الشخصية (Custody vs Salary Advance):
- عهد المواقع (حساب 1120) أموال للشركة مخصصة لمصروفات الموقع ولا تخصم تلقائياً من الراتب.
- السلف الشخصية (مسحوبات شخصية) تسجل عبر record_salary_advance_deduction في مسير الرواتب (Additional Salary) وتستقطع حصراً من راتب الموظف.

7. الفصل بين الأرصدة المقيدة بالدفاتر والمسودات:
- اعتمد حصراً على حركات الأستاذ العام (GL Entry) المرحّلة لحساب رصيد العهدة الفعلي.
- لا تعامل مسودات القيود (Draft) كحركات دفترية مرحلة، وأظهر إجمالي المسودات بشكل منفصل تماماً.""",
        "functions": [
            "get_chart_of_accounts_tree",
            "get_cost_centers_tree",
            "get_projects_list",
            "get_gl_balance",
            "create_draft_journal_entry",
            "create_contractor_purchase_invoice",
            "create_custody_settlement_entry",
            "get_project_financial_summary",
            "get_journal_entry_list",
            "get_payment_entry_list",
            "get_sales_invoice_list",
            "get_purchase_invoice_list",
            "get_customer_list",
            "get_supplier_list",
            "get_employee_advance_list",
            "get_expense_claim_list",
            "get_employee_custody_report",
            "simulate_employee_custody_workflow",
            "record_employee_custody_expense",
            "record_salary_advance_deduction",
            "inspect_and_propose_jv_correction"
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
2. ضع روابط المستندات دائماً على أسطر منفصلة بمفردها (https://erp.elsaidy.org/app/...).
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
        "description": "المساعد الذكي للمستودعات وإدارة المواد لنظام Elsaidy ERP",
        "temperature": 0.02,
        "top_p": 1.00,
        "instruction": """أنت المساعد الذكي لإدارة المستودعات وحركات المخزون والمهمات الإنشائية لنظام Elsaidy ERP في شركة ركن سبل الأفق للمقاولات.

سياق النظام الحي:
- الشركة: {{ company }}
- المستخدم: {{ user }}

قواعد التنسيق والعمل:
1. اذكر الكميات المتوفرة والمحجوزة بدقة مع تحديد المستودع.
2. استخدم الرموز التعبيرية النقطية واللغة العربية الواضحة وتجنب علامات الماركداون العكسية على الأرقام.
3. ضع الروابط المباشرة على أسطر منفصلة.""",
        "functions": [
            "get_warehouse_stock",
            "get_item_list",
            "get_warehouse_list",
            "get_material_request_list",
            "get_purchase_receipt_list",
            "get_delivery_note_list",
            "get_stock_entry_list",
            "get_item_price_list",
            "get_stock_ledger_list"
        ]
    },
    "Projects": {
        "description": "المساعد الذكي لإدارة المشاريع ومواقع المقاولات لنظام Elsaidy ERP",
        "temperature": 0.02,
        "top_p": 1.00,
        "instruction": """أنت المساعد الذكي لإدارة المشاريع الإنشائية ومواقع المقاولات الميدانية لنظام Elsaidy ERP في شركة ركن سبل الأفق للمقاولات.

سياق النظام الحي:
- الشركة: {{ company }}
- المستخدم: {{ user }}

قواعد التنسيق والعمل:
1. استعرض تفاصيل المشاريع الإنشائية ومراكز التكلفة ونسب الإنجاز.
2. استخدم أداة get_project_financial_summary لتقديم كشف فوري بالأداء المالي للمشاريع (الإيرادات والتكاليف ومحجوزات الضمان).
3. اعرض روابط المشاريع المباشرة على أسطر منفصلة (https://erp.elsaidy.org/app/project/...).""",
        "functions": [
            "get_projects_list",
            "get_project_financial_summary",
            "get_project_task_list",
            "get_cost_centers_tree",
            "get_gl_balance"
        ]
    },
    "HR": {
        "description": "المساعد الذكي للموارد البشرية والشؤون الإدارية لنظام Elsaidy ERP",
        "temperature": 0.02,
        "top_p": 1.00,
        "instruction": """أنت المساعد الذكي لقطاع الموارد البشرية والشؤون الإدارية (HR & Administrative Assistant) لنظام Elsaidy ERP في شركة ركن سبل الأفق للمقاولات.

سياق النظام الحي:
- الشركة: {{ company }}
- المستخدم: {{ user }}

قواعد التنسيق والعمل:
1. استعرض بيانات الموظفين، الإجازات، الحضور، ومطالبات المصروفات وفق نظام العمل السعودي والتأمينات الاجتماعية (GOSI).
2. استخدم لغة عربية مهنية وتنسيق نقطي واضح مع روابط مباشرة على أسطر مستقلة.""",
        "functions": [
            "get_employee_info",
            "get_leaves_summary",
            "get_expense_claim_list",
            "get_employee_advance_list"
        ]
    },
    "Support": {
        "description": "المساعد الذكي للدعم الفني والعمليات التشغيلية لنظام Elsaidy ERP",
        "temperature": 0.02,
        "top_p": 1.00,
        "instruction": """أنت المساعد الذكي للدعم الفني وخدمة المستخدمين الداخليين والعملاء لنظام Elsaidy ERP في شركة ركن سبل الأفق للمقاولات.

سياق النظام الحي:
- الشركة: {{ company }}
- المستخدم: {{ user }}

قواعد التنسيق والعمل:
1. قدم الدعم والإجابة على استفسارات المستخدمين حول النظام، التذاكر، والمشكلات التقنية.
2. استخدم أسلوباً احترافياً وتنسيقاً عربياً منظماً.""",
        "functions": [
            "get_hd_ticket_list",
            "get_user_info",
            "get_system_status"
        ]
    },
    "Test": {
        "description": "بوت الاختبار والتحقق الشامل من تكامل نظام Elsaidy ERP",
        "temperature": 0.00,
        "top_p": 1.00,
        "instruction": """أنت وكيل الاختبار والتدقيق التقني لنظام Elsaidy ERP.
مهمتك إجراء عمليات الفحص والاختبار للتكاملات والأدوات والتأكد من استقرار بيئة العمل وسلامة البيانات.""",
        "functions": [
            "get_chart_of_accounts_tree",
            "get_cost_centers_tree",
            "get_projects_list",
            "get_gl_balance",
            "create_draft_journal_entry"
        ]
    }
}


CHANNELS_CONFIG = [
    {
        "channel_name": "general",
        "channel_id": "raven-general",
        "description": "القناة العامة لشركة ركن سبل الأفق للمقاولات - Elsaidy ERP",
        "type": "Open",
        "bot": "Accounting"
    },
    {
        "channel_name": "accounting",
        "channel_id": "raven-accounting",
        "description": "قناة الإدارة المالية والمحاسبية والمستخلصات - Elsaidy Accounting",
        "type": "Open",
        "bot": "Accounting"
    },
    {
        "channel_name": "sales",
        "channel_id": "raven-sales",
        "description": "قناة المبيعات وعلاقات العملاء والمناقصات - Elsaidy CRM & Sales",
        "type": "Open",
        "bot": "Sales"
    },
    {
        "channel_name": "projects",
        "channel_id": "raven-projects",
        "description": "قناة إدارة المشاريع والعمليات الميدانية - Elsaidy Projects",
        "type": "Open",
        "bot": "Projects"
    },
    {
        "channel_name": "hr",
        "channel_id": "raven-hr",
        "description": "قناة الموارد البشرية وشؤون الموظفين - Elsaidy HR",
        "type": "Open",
        "bot": "HR"
    },
    {
        "channel_name": "inventory",
        "channel_id": "raven-inventory",
        "description": "قناة إدارة المستودعات والمهمات الإنشائية - Elsaidy Inventory",
        "type": "Open",
        "bot": "Inventory"
    }
]


DOCUMENT_NOTIFICATIONS = [
    {
        "name": "إشعار اعتماد قيد يومية",
        "document_type": "Journal Entry",
        "event": "On Submit",
        "channel": "raven-accounting",
        "template": "تم اعتماد قيد اليومية رقم {{ doc.name }} بقيمة {{ doc.total_debit }} ريال سعودي بواسطة {{ doc.modified_by }}."
    },
    {
        "name": "إشعار اعتماد فاتورة مبيعات",
        "document_type": "Sales Invoice",
        "event": "On Submit",
        "channel": "raven-sales",
        "template": "تم إصدار واعتماد فاتورة مبيعات / مستخلص رقم {{ doc.name }} للعميل {{ doc.customer }} بقيمة {{ doc.grand_total }} ريال."
    },
    {
        "name": "إشعار اعتماد أمر شراء",
        "document_type": "Purchase Order",
        "event": "On Submit",
        "channel": "raven-inventory",
        "template": "تم اعتماد أمر الشراء رقم {{ doc.name }} للمورد {{ doc.supplier }} بقيمة إجمالية {{ doc.grand_total }} ريال."
    },
    {
        "name": "إشعار مطالبة مصروفات جديدة",
        "document_type": "Expense Claim",
        "event": "After Insert",
        "channel": "raven-hr",
        "template": "تم تقديم مطالبة مصروفات جديدة رقم {{ doc.name }} من الموظف {{ doc.employee_name }} بقيمة {{ doc.total_claimed_amount }} ريال."
    },
    {
        "name": "إشعار تسجيل بلاغ أو مشكلة جديدة",
        "document_type": "Issue",
        "event": "After Insert",
        "channel": "raven-general",
        "template": "تم تسجيل بلاغ جديد رقم {{ doc.name }}: {{ doc.subject }} - الأولوية: {{ doc.priority }}."
    }
]


MESSAGE_ACTIONS = [
    {
        "action_name": "Create Task from Message",
        "title": "Create Task",
        "document_type": "Task",
        "target_doctype": "Task",
        "description": "تحويل الرسالة إلى مهمة عمل في النظام"
    },
    {
        "action_name": "Create Issue from Message",
        "title": "Create Issue",
        "document_type": "Issue",
        "target_doctype": "Issue",
        "description": "تحويل الرسالة إلى بلاغ دعم فني أو مشكلة تشغيلية"
    },
    {
        "action_name": "Create ToDo from Message",
        "title": "Create ToDo",
        "document_type": "ToDo",
        "target_doctype": "ToDo",
        "description": "إنشاء تذكرة عمل سريعة (ToDo) من الرسالة"
    }
]


def sync_saudi_accounting_preset():
    """
    Creates/updates specialized Saudi Contracting Chart of Accounts and Tax Templates for Rkn.
    """
    print("\n[Elsaidy ERP] Synchronizing Saudi Contracting COA & ZATCA Accounts...")
    companies = frappe.get_all("Company", fields=["name", "abbr"])
    if not companies:
        print(" -> No Company found, skipping COA sync.")
        return
    target_comp = None
    for c in companies:
        if "ركن" in c.name or "سبل" in c.name:
            target_comp = c
            break
    if not target_comp:
        target_comp = companies[0]

    comp = target_comp.name
    abbr = target_comp.abbr

    new_accounts = [
        {"account_name": "مصروف الوقود والمحروقات", "account_number": "5120", "parent_account": f"5100 - النفقات المباشرة - {abbr}", "root_type": "Expense", "account_type": "Expense Account"},
        {"account_name": "صيانة وإصلاح السيارات والمعدات", "account_number": "5130", "parent_account": f"5100 - النفقات المباشرة - {abbr}", "root_type": "Expense", "account_type": "Expense Account"},
        {"account_name": "إيجار معدات وآليات ثقيلة", "account_number": "5140", "parent_account": f"5100 - النفقات المباشرة - {abbr}", "root_type": "Expense", "account_type": "Expense Account"},
        {"account_name": "مواد ومهمات تشغيل المشاريع", "account_number": "5150", "parent_account": f"5100 - النفقات المباشرة - {abbr}", "root_type": "Expense", "account_type": "Expense Account"},
        {"account_name": "أعمال مقاولي الباطن", "account_number": "5160", "parent_account": f"5100 - النفقات المباشرة - {abbr}", "root_type": "Expense", "account_type": "Expense Account"},
        {"account_name": "ضيافة وإعاشة مواقع", "account_number": "5170", "parent_account": f"5100 - النفقات المباشرة - {abbr}", "root_type": "Expense", "account_type": "Expense Account"},
        {"account_name": "رسوم حكومية وتراخيص بلدية", "account_number": "5230", "parent_account": f"5200 - نفقات غير مباشرة - {abbr}", "root_type": "Expense", "account_type": "Expense Account"},
        {"account_name": "ضريبة القيمة المضافة للمخرجات 15%", "account_number": "2330", "parent_account": f"2300 - الرسوم والضرائب - {abbr}", "root_type": "Liability", "account_type": "Tax", "tax_rate": 15.0},
        {"account_name": "ضريبة القيمة المضافة للمدخلات 15%", "account_number": "1510", "parent_account": f"1500 - ضريبية الأصول - {abbr}", "root_type": "Asset", "account_type": "Tax", "tax_rate": 15.0},
        {"account_name": "ضريبة مدخلات معلقة تحت المراجعة والاعتماد", "account_number": "1520", "parent_account": f"1500 - ضريبية الأصول - {abbr}", "root_type": "Asset", "account_type": "Tax", "tax_rate": 15.0},
        {"account_name": "ضريبة مدخلات غير قابلة للاسترداد", "account_number": "5235", "parent_account": f"5200 - نفقات غير مباشرة - {abbr}", "root_type": "Expense", "account_type": "Expense Account"},
        {"account_name": "محجوزات ضمان حسن التنفيذ للعملاء (Retention)", "account_number": "1320", "parent_account": f"1300 - الحسابات المدينة - {abbr}", "root_type": "Asset", "account_type": "Receivable"},
        {"account_name": "محجوزات ضمان مقاولي الباطن", "account_number": "2130", "parent_account": f"2100 - الحسابات الدائنة - {abbr}", "root_type": "Liability", "account_type": "Payable"},
        {"account_name": "عهد نقدية للمهندسين والمشرفين", "account_number": "1120", "parent_account": f"1100 - النقدية الحاضرة - {abbr}", "root_type": "Asset", "account_type": "Cash"}
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
                doc.insert(ignore_permissions=True)
                print(f" -> Created Account: {acc_full_name}")
            except Exception as e:
                print(f" -> Warning creating Account {acc_full_name}: {e}")
        else:
            print(f" -> Account exists: {acc_full_name}")

    frappe.db.commit()

    output_tax_acc = f"2330 - ضريبة القيمة المضافة للمخرجات 15% - {abbr}"
    input_tax_acc = f"1510 - ضريبة القيمة المضافة للمدخلات 15% - {abbr}"
    tax_tmpl_title = f"ضريبة القيمة المضافة السعودية 15% - {abbr}"

    if not frappe.db.exists("Sales Taxes and Charges Template", {"title": tax_tmpl_title}):
        try:
            st = frappe.new_doc("Sales Taxes and Charges Template")
            st.title = tax_tmpl_title
            st.company = comp
            st.is_default = 1
            st.append("taxes", {
                "charge_type": "On Net Total",
                "account_head": output_tax_acc,
                "description": "ضريبة القيمة المضافة 15% (ZATCA)",
                "rate": 15.0
            })
            st.insert(ignore_permissions=True)
            print(f" -> Created Sales Tax Template: {tax_tmpl_title}")
        except Exception as e:
            print(f" -> Warning creating Sales Tax Template: {e}")
    else:
        print(f" -> Sales Tax Template exists: {tax_tmpl_title}")

    if not frappe.db.exists("Purchase Taxes and Charges Template", {"title": tax_tmpl_title}):
        try:
            pt = frappe.new_doc("Purchase Taxes and Charges Template")
            pt.title = tax_tmpl_title
            pt.company = comp
            pt.is_default = 1
            pt.append("taxes", {
                "charge_type": "On Net Total",
                "account_head": input_tax_acc,
                "description": "ضريبة القيمة المضافة 15% المستردة (ZATCA)",
                "rate": 15.0
            })
            pt.insert(ignore_permissions=True)
            print(f" -> Created Purchase Tax Template: {tax_tmpl_title}")
        except Exception as e:
            print(f" -> Warning creating Purchase Tax Template: {e}")
    else:
        print(f" -> Purchase Tax Template exists: {tax_tmpl_title}")

    frappe.db.commit()


def sync_saudi_print_formats():
    """
    Creates and configures bilingual, ZATCA-compliant Print Formats for Sales Invoices and Contracting IPCs.
    """
    print("\n[Elsaidy ERP] Synchronizing Print Formats (Invoice & IPC)...")

    # 1. Elsaidy Saudi Contracting Invoice
    pf_name = "Elsaidy Saudi Contracting Invoice"
    invoice_html = """
<div class="zatca-invoice" dir="rtl">
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;800&display=swap');
    .zatca-invoice {
        font-family: 'Cairo', 'Segoe UI', Tahoma, sans-serif;
        color: #0f172a;
        background: #ffffff;
        padding: 24px;
        line-height: 1.5;
        direction: rtl;
    }
    .invoice-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        border-bottom: 3px solid #1e3a8a;
        padding-bottom: 16px;
        margin-bottom: 20px;
    }
    .company-meta h2 {
        margin: 0 0 6px 0;
        font-size: 22px;
        font-weight: 800;
        color: #1e3a8a;
    }
    .badge-id {
        display: inline-block;
        background: #f1f5f9;
        color: #0f172a;
        padding: 3px 8px;
        border-radius: 6px;
        font-size: 11px;
        font-weight: 700;
        margin-left: 6px;
        border: 1px solid #cbd5e1;
    }
    .invoice-title-box {
        text-align: left;
    }
    .invoice-title {
        font-size: 20px;
        font-weight: 800;
        color: #d97706;
        margin: 0;
    }
    .invoice-grid {
        display: flex;
        justify-content: space-between;
        gap: 15px;
        margin-bottom: 20px;
    }
    .info-box {
        flex: 1;
        background: #f8fafc;
        border: 1px solid #e2e8f0;
        border-radius: 8px;
        padding: 12px;
        font-size: 12px;
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
        width: 35%;
    }
    .zatca-table {
        width: 100%;
        border-collapse: collapse;
        margin: 15px 0;
    }
    .zatca-table th {
        background-color: #1e3a8a;
        color: #ffffff;
        font-weight: 700;
        padding: 10px 8px;
        font-size: 12px;
        border: 1px solid #1e3a8a;
        text-align: center;
    }
    .zatca-table td {
        border: 1px solid #cbd5e1;
        padding: 8px;
        font-size: 12px;
        text-align: center;
    }
    .totals-container {
        display: flex;
        justify-content: space-between;
        gap: 20px;
        margin-top: 15px;
    }
    .qr-box {
        width: 160px;
        text-align: center;
        border: 1px solid #cbd5e1;
        border-radius: 8px;
        padding: 8px;
        background: #fafafa;
    }
    .totals-table {
        width: 320px;
        border-collapse: collapse;
        font-size: 12px;
    }
    .totals-table td {
        padding: 6px 10px;
        border: 1px solid #e2e8f0;
    }
    .grand-total-row {
        background: #1e3a8a;
        color: #ffffff;
        font-weight: 800;
        font-size: 14px;
    }
    .signatures-grid {
        display: flex;
        justify-content: space-between;
        margin-top: 30px;
        text-align: center;
        font-size: 12px;
    }
    .sig-box {
        flex: 1;
        border-top: 1px dashed #94a3b8;
        padding-top: 8px;
        margin: 0 10px;
    }
    </style>

    <div class="invoice-header">
        <div class="company-meta">
            <h2>شركة ركن سبل الأفق للمقاولات <span style="font-size: 13px; color: #d97706;">(Elsaidy Contracting)</span></h2>
            <div>
                <span class="badge-id">سجل تجاري (CR): 1010000000</span>
                <span class="badge-id">الرقم الضريبي (VAT ID): 300000000000003</span>
            </div>
            <div style="font-size: 11px; color: #64748b; margin-top: 4px;">المملكة العربية السعودية - الرياض | هاتف: +966569589664</div>
        </div>
        <div class="invoice-title-box">
            <h3 class="invoice-title">فاتورة ضريبية / TAX INVOICE</h3>
            <div style="font-size: 12px; font-weight: 700; color: #1e3a8a;">رقم الفاتورة: {{ doc.name }}</div>
            <div style="font-size: 11px; color: #64748b;">تاريخ الإصدار: {{ doc.posting_date }}</div>
        </div>
    </div>

    <div class="invoice-grid">
        <div class="info-box">
            <div style="font-weight: 800; color: #1e3a8a; margin-bottom: 6px; border-bottom: 1px solid #cbd5e1; padding-bottom: 4px;">بيانات العميل / Customer Details</div>
            <table class="info-table">
                <tr><td class="info-label">العميل:</td><td>{{ doc.customer_name or doc.customer }}</td></tr>
                <tr><td class="info-label">الرقم الضريبي:</td><td>{{ doc.tax_id or '-' }}</td></tr>
                <tr><td class="info-label">العنوان:</td><td>{{ doc.address_display or '-' }}</td></tr>
            </table>
        </div>
        <div class="info-box">
            <div style="font-weight: 800; color: #1e3a8a; margin-bottom: 6px; border-bottom: 1px solid #cbd5e1; padding-bottom: 4px;">بيانات المشروع والعقد / Project & IPC</div>
            <table class="info-table">
                <tr><td class="info-label">المشروع:</td><td>{{ doc.project or '-' }}</td></tr>
                <tr><td class="info-label">مركز التكلفة:</td><td>{{ doc.cost_center or '-' }}</td></tr>
                <tr><td class="info-label">نوع المستخلص:</td><td>{{ doc.custom_ipc_type or 'فاتورة ضريبية' }}</td></tr>
                <tr><td class="info-label">رقم المستخلص:</td><td>{{ doc.custom_ipc_number or '-' }}</td></tr>
            </table>
        </div>
    </div>

    <table class="zatca-table">
        <thead>
            <tr>
                <th style="width: 5%;">#</th>
                <th style="width: 45%;">البند والوصف / Description</th>
                <th style="width: 10%;">الكمية / Qty</th>
                <th style="width: 12%;">السعر / Price</th>
                <th style="width: 13%;">الضريبة / 15% VAT</th>
                <th style="width: 15%;">الإجمالي / Total</th>
            </tr>
        </thead>
        <tbody>
            {% for row in doc.items %}
            <tr>
                <td>{{ loop.index }}</td>
                <td style="text-align: right;"><strong>{{ row.item_name }}</strong><br><small style="color: #64748b;">{{ row.description }}</small></td>
                <td>{{ row.qty }} {{ row.uom }}</td>
                <td>{{ "{:,.2f}".format(row.rate) }}</td>
                <td>{{ "{:,.2f}".format(row.amount * 0.15) }}</td>
                <td style="font-weight: 700;">{{ "{:,.2f}".format(row.amount * 1.15) }} SAR</td>
            </tr>
            {% endfor %}
        </tbody>
    </table>

    <div class="totals-container">
        <div class="qr-box">
            {% if doc.qr_code %}
            <img src="{{ doc.qr_code }}" style="width: 130px; height: 130px;" alt="ZATCA QR">
            {% else %}
            <div style="width: 130px; height: 130px; border: 1px dashed #cbd5e1; margin: auto; display: flex; align-items: center; justify-content: center; font-size: 10px; color: #94a3b8;">رمز ZATCA QR المعتمد</div>
            {% endif %}
            <div style="font-size: 9px; font-weight: 700; color: #1e3a8a; margin-top: 4px;">متوافق مع هيئة الزكاة والضريبة</div>
        </div>
        <table class="totals-table">
            <tr><td>الإجمالي الخاضع للضريبة (SAR):</td><td style="text-align: left; font-weight: 700;">{{ "{:,.2f}".format(doc.base_total) }}</td></tr>
            {% if doc.custom_advance_recovery_amount %}
            <tr><td>يخصم: استرداد دفعة مقدمة:</td><td style="text-align: left; color: #dc2626;">- {{ "{:,.2f}".format(doc.custom_advance_recovery_amount) }}</td></tr>
            {% endif %}
            {% if doc.custom_retention_amount %}
            <tr><td>يخصم: محجوز الضمان (10%):</td><td style="text-align: left; color: #dc2626;">- {{ "{:,.2f}".format(doc.custom_retention_amount) }}</td></tr>
            {% endif %}
            <tr><td>ضريبة القيمة المضافة 15%:</td><td style="text-align: left; font-weight: 700; color: #d97706;">{{ "{:,.2f}".format(doc.total_taxes_and_charges) }}</td></tr>
            <tr class="grand-total-row"><td>صافي المستحق النهائي (SAR):</td><td style="text-align: left;">{{ "{:,.2f}".format(doc.base_grand_total) }}</td></tr>
        </table>
    </div>

    <div style="margin-top: 15px; padding: 10px; background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; font-size: 11px;">
        <strong>الحساب البنكي المعتمد:</strong> البنك الأهلي السعودي (SNB) | الآيبان: SA0000000000000000000000 | باسم: شركة ركن سبل الأفق للمقاولات
    </div>

    <div class="signatures-grid">
        <div class="sig-box">إعداد ومراجعة الحسابات<br><br><strong>المحاسب المسؤول</strong></div>
        <div class="sig-box">مدير المشروع الميداني<br><br><strong>مهندس الموقع</strong></div>
        <div class="sig-box">الاعتماد النهائي والختم<br><br><strong>المدير العام / المفوض</strong></div>
    </div>
</div>
"""
    if frappe.db.exists("Print Format", pf_name):
        doc = frappe.get_doc("Print Format", pf_name)
    else:
        doc = frappe.new_doc("Print Format")
        doc.name = pf_name
        doc.doc_type = "Sales Invoice"
        doc.module = "Accounts"
        doc.standard = "No"
        doc.custom_format = 1
        doc.print_format_type = "Jinja"

    doc.html = invoice_html
    doc.default_print_language = "ar"
    doc.save(ignore_permissions=True)
    print(f" -> Configured Print Format: {pf_name}")

    # 2. مستخلص أعمال مقاولات معتمد (Certified Saudi IPC Certificate)
    ipc_pf_name = "مستخلص أعمال مقاولات معتمد"
    ipc_html = """
<div class="ipc-certificate" dir="rtl">
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;800&display=swap');
    .ipc-certificate {
        font-family: 'Cairo', 'Segoe UI', Tahoma, sans-serif;
        color: #0f172a;
        background: #ffffff;
        padding: 24px;
        line-height: 1.5;
        direction: rtl;
    }
    .ipc-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        border-bottom: 4px solid #1e3a8a;
        padding-bottom: 15px;
        margin-bottom: 20px;
    }
    .ipc-title-main {
        text-align: center;
        background: #1e3a8a;
        color: #ffffff;
        padding: 8px 15px;
        border-radius: 8px;
        font-size: 18px;
        font-weight: 800;
        margin: 15px 0;
    }
    .ipc-grid-3 {
        display: flex;
        gap: 12px;
        margin-bottom: 15px;
    }
    .ipc-card {
        flex: 1;
        background: #f8fafc;
        border: 1px solid #cbd5e1;
        border-radius: 8px;
        padding: 10px;
        font-size: 11px;
    }
    .ipc-table {
        width: 100%;
        border-collapse: collapse;
        margin: 15px 0;
        font-size: 11px;
    }
    .ipc-table th {
        background: #0f172a;
        color: #ffffff;
        padding: 8px;
        border: 1px solid #0f172a;
        text-align: center;
    }
    .ipc-table td {
        border: 1px solid #cbd5e1;
        padding: 6px;
        text-align: center;
    }
    .ipc-calc-box {
        width: 100%;
        border-collapse: collapse;
        margin: 15px 0;
        font-size: 12px;
    }
    .ipc-calc-box td {
        padding: 7px 12px;
        border: 1px solid #cbd5e1;
    }
    .ipc-calc-title {
        background: #f1f5f9;
        font-weight: 700;
        width: 60%;
    }
    .ipc-calc-val {
        text-align: left;
        font-weight: 700;
    }
    .ipc-highlight {
        background: #1e3a8a;
        color: #ffffff;
        font-size: 14px;
        font-weight: 800;
    }
    .ipc-signatures {
        display: flex;
        justify-content: space-between;
        margin-top: 35px;
        text-align: center;
        font-size: 11px;
    }
    .ipc-sig {
        flex: 1;
        border-top: 1px dashed #64748b;
        padding-top: 8px;
        margin: 0 8px;
    }
    </style>

    <div class="ipc-header">
        <div>
            <h2 style="margin: 0; color: #1e3a8a; font-weight: 800; font-size: 22px;">شركة ركن سبل الأفق للمقاولات</h2>
            <div style="color: #d97706; font-weight: 700; font-size: 13px;">قطاع المشروعات والتنفيذ الإنشائي | Elsaidy Contracting</div>
            <div style="font-size: 11px; color: #64748b; margin-top: 3px;">سجل تجاري: 1010000000 | الرقم الضريبي: 300000000000003</div>
        </div>
        <div style="text-align: left;">
            <div style="font-size: 14px; font-weight: 800; color: #1e3a8a;">رقم المستخلص: {{ doc.custom_ipc_number or doc.name }}</div>
            <div style="font-size: 12px; color: #64748b;">تاريخ التقديم: {{ doc.posting_date }}</div>
            <div style="font-size: 12px; font-weight: 700; color: #d97706;">النوع: {{ doc.custom_ipc_type or 'مستخلص جاري' }}</div>
        </div>
    </div>

    <div class="ipc-title-main">
        شهادة مستخلص أعمال مقاولات معتمد (INTERIM PAYMENT CERTIFICATE - IPC)
    </div>

    <div class="ipc-grid-3">
        <div class="ipc-card">
            <strong>المالك / صاحب العمل:</strong><br>
            {{ doc.customer_name or doc.customer }}<br>
            <small style="color: #64748b;">الرقم الضريبي: {{ doc.tax_id or '-' }}</small>
        </div>
        <div class="ipc-card">
            <strong>المشروع وموقع العمل:</strong><br>
            {{ doc.project or '-' }}<br>
            <small style="color: #64748b;">مركز التكلفة: {{ doc.cost_center or '-' }}</small>
        </div>
        <div class="ipc-card">
            <strong>قيمة العقد المعتمد:</strong><br>
            <span style="font-size: 13px; font-weight: 800; color: #1e3a8a;">{{ "{:,.2f}".format(doc.custom_contract_value or 0.0) }} SAR</span><br>
            <small style="color: #64748b;">نسبة ضمان الأعمال: {{ doc.custom_retention_pct or 10 }}%</small>
        </div>
    </div>

    <table class="ipc-table">
        <thead>
            <tr>
                <th style="width: 5%;">#</th>
                <th style="width: 45%;">بيان الأعمال وبنود المقايسة</th>
                <th style="width: 10%;">الوحدة</th>
                <th style="width: 12%;">الكمية المنفذة</th>
                <th style="width: 13%;">فئة البند (SAR)</th>
                <th style="width: 15%;">قيمة الأعمال (SAR)</th>
            </tr>
        </thead>
        <tbody>
            {% for row in doc.items %}
            <tr>
                <td>{{ loop.index }}</td>
                <td style="text-align: right;"><strong>{{ row.item_name }}</strong><br><small>{{ row.description }}</small></td>
                <td>{{ row.uom }}</td>
                <td>{{ row.qty }}</td>
                <td>{{ "{:,.2f}".format(row.rate) }}</td>
                <td style="font-weight: 700;">{{ "{:,.2f}".format(row.amount) }}</td>
            </tr>
            {% endfor %}
        </tbody>
    </table>

    <table class="ipc-calc-box">
        <tr><td class="ipc-calc-title">1. إجمالي قيمة الأعمال المنجزة حتى تاريخه (Gross Executed Work):</td><td class="ipc-calc-val">{{ "{:,.2f}".format(doc.base_total) }} SAR</td></tr>
        <tr><td class="ipc-calc-title">2. يخصم: إجمالي المستخلصات السابقة المصروفة (Less Previous IPCs Paid):</td><td class="ipc-calc-val" style="color: #dc2626;">- {{ "{:,.2f}".format(doc.custom_previous_ipc_total or 0.0) }} SAR</td></tr>
        <tr><td class="ipc-calc-title">3. يخصم: استرداد الدفعة المقدمة (Less Advance Recovery {{ doc.custom_advance_recovery_pct or 0 }}%):</td><td class="ipc-calc-val" style="color: #dc2626;">- {{ "{:,.2f}".format(doc.custom_advance_recovery_amount or 0.0) }} SAR</td></tr>
        <tr><td class="ipc-calc-title">4. يخصم: محجوز ضمان حسن التنفيذ (Less Retention {{ doc.custom_retention_pct or 10 }}%):</td><td class="ipc-calc-val" style="color: #dc2626;">- {{ "{:,.2f}".format(doc.custom_retention_amount or 0.0) }} SAR</td></tr>
        <tr><td class="ipc-calc-title">5. صافي المبلغ الخاضع للضريبة لهذا المستخلص (Net Taxable Base):</td><td class="ipc-calc-val">{{ "{:,.2f}".format(doc.base_net_total or (doc.base_total - (doc.custom_previous_ipc_total or 0.0))) }} SAR</td></tr>
        <tr><td class="ipc-calc-title">6. يضاف: ضريبة القيمة المضافة 15% (Plus 15% ZATCA VAT):</td><td class="ipc-calc-val" style="color: #d97706;">+ {{ "{:,.2f}".format(doc.total_taxes_and_charges) }} SAR</td></tr>
        <tr class="ipc-highlight"><td style="color: #ffffff;">7. صافي المبلغ المعتمد للصرف للمقاول (Net Amount Payable to Contractor):</td><td class="ipc-calc-val" style="color: #ffffff; font-size: 15px;">{{ "{:,.2f}".format(doc.base_grand_total) }} SAR</td></tr>
    </table>

    <div class="ipc-signatures">
        <div class="ipc-sig">مهندس الموقع / المقاول<br><br><strong>مهندس التنفيذ</strong></div>
        <div class="ipc-sig">الاستشاري المشرف على المشروع<br><br><strong>مهندس الإشراف</strong></div>
        <div class="ipc-sig">الإدارة المالية والمراجعة<br><br><strong>المدير المالي</strong></div>
        <div class="ipc-sig">اعتماد المالك / المفوض بالصرف<br><br><strong>صاحب العمل / المدير العام</strong></div>
    </div>
</div>
"""
    for doctype in ["Sales Invoice", "Purchase Invoice"]:
        custom_ipc_name = f"{ipc_pf_name} - {doctype}"
        if frappe.db.exists("Print Format", custom_ipc_name):
            doc = frappe.get_doc("Print Format", custom_ipc_name)
        else:
            doc = frappe.new_doc("Print Format")
            doc.name = custom_ipc_name
            doc.doc_type = doctype
            doc.module = "Accounts"
            doc.standard = "No"
            doc.custom_format = 1
            doc.print_format_type = "Jinja"

        doc.html = ipc_html
        doc.default_print_language = "ar"
        doc.save(ignore_permissions=True)
        print(f" -> Configured Print Format: {custom_ipc_name}")

    frappe.db.commit()


def sync_whitelabel_and_branding():
    """
    Applies 100% white-labeling across System Settings, Website Settings, and Navbar Settings.
    """
    print("\n[Elsaidy ERP] Synchronizing 100% White-Label Branding...")
    logo_svg = "/assets/hagag_erp/images/elsaidy_logo.svg"
    icon_svg = "/assets/hagag_erp/images/elsaidy_icon.svg"

    try:
        ss = frappe.get_single("System Settings")
        ss.app_name = "Elsaidy ERP"
        ss.disable_system_update_notification = 1
        ss.disable_change_log_notification = 1
        ss.enable_onboarding = 0
        ss.save(ignore_permissions=True)
        print(" -> Configured System Settings.")
    except Exception as e:
        print(f" -> Warning configuring System Settings: {e}")

    try:
        ws = frappe.get_single("Website Settings")
        ws.app_name = "Elsaidy ERP"
        ws.title_prefix = "Elsaidy ERP"
        ws.app_logo = logo_svg
        ws.banner_image = logo_svg
        ws.splash_image = logo_svg
        ws.favicon = icon_svg
        ws.save(ignore_permissions=True)
        print(" -> Configured Website Settings.")
    except Exception as e:
        print(f" -> Warning configuring Website Settings: {e}")

    try:
        ns = frappe.get_single("Navbar Settings")
        ns.app_logo = logo_svg
        hidden_labels = ["About", "Documentation", "User Forum", "Report an Issue", "Frappe Support", "System Health"]
        for item in ns.help_dropdown:
            if item.item_label in hidden_labels or "support" in (item.item_label or "").lower():
                item.hidden = 1
        ns.save(ignore_permissions=True)
        print(" -> Configured Navbar Settings.")
    except Exception as e:
        print(f" -> Warning configuring Navbar Settings: {e}")

    frappe.db.commit()


def sync_desktop_icons_and_translations():
    """
    Updates Desktop Icons and tabTranslation to remove Frappe/Hagag names everywhere on /desk.
    """
    print("\n[Elsaidy ERP] Synchronizing Desktop Icons & Translations...")
    icon_map = {
        "Framework": "Elsaidy Core | النظام الأساسي",
        "ERPNext": "Elsaidy ERP",
        "ERPNext Settings": "إعدادات Elsaidy ERP",
        "Frappe HR": "Elsaidy HR",
        "Frappe CRM": "Elsaidy CRM",
        "Helpdesk": "Elsaidy Support",
        "Insights": "Elsaidy BI & Insights",
        "Frappe Builder": "Elsaidy Builder",
        "Wiki": "Elsaidy Wiki"
    }
    for icon_name, new_label in icon_map.items():
        if frappe.db.exists("Desktop Icon", icon_name):
            frappe.db.set_value("Desktop Icon", icon_name, "label", new_label)

    trans_entries = [
        ("ar", "Framework", "Elsaidy Core | النظام الأساسي"),
        ("ar", "Frappe Framework", "Elsaidy Core | النظام الأساسي"),
        ("ar", "إطار العمل", "Elsaidy Core | النظام الأساسي"),
        ("ar", "ERPNext", "Elsaidy ERP"),
        ("ar", "Erp Elsaidy", "Elsaidy ERP"),
        ("ar", "Frappe HR", "Elsaidy HR"),
        ("ar", "Frappe CRM", "Elsaidy CRM"),
        ("ar", "إدارة علاقات العملاء", "Elsaidy CRM"),
        ("ar", "Frappe Helpdesk", "Elsaidy Support"),
        ("ar", "Helpdesk", "Elsaidy Support"),
        ("ar", "Frappe Insights", "Elsaidy BI & Insights"),
        ("ar", "Insights", "Elsaidy BI & Insights"),
        ("ar", "Frappe Builder", "Elsaidy Builder"),
        ("ar", "Builder", "Elsaidy Builder"),
        ("ar", "Frappe Wiki", "Elsaidy Wiki"),
        ("ar", "Wiki", "Elsaidy Wiki"),
        ("ar", "Raven", "Elsaidy AI (Raven)"),
        ("ar", "شركة حجاج", "شركة ركن سبل الأفق للمقاولات"),
        ("ar", "حجاج", "الصعيدي"),
        ("ar", "Hagag", "Elsaidy"),
        ("ar", "Frappe", "Elsaidy"),
        ("en", "Framework", "Elsaidy Core"),
        ("en", "Frappe Framework", "Elsaidy Core"),
        ("en", "ERPNext", "Elsaidy ERP"),
        ("en", "Frappe HR", "Elsaidy HR"),
        ("en", "Frappe CRM", "Elsaidy CRM"),
        ("en", "Frappe Helpdesk", "Elsaidy Support"),
        ("en", "Helpdesk", "Elsaidy Support"),
        ("en", "Frappe Insights", "Elsaidy BI & Insights"),
        ("en", "Insights", "Elsaidy BI & Insights"),
        ("en", "Frappe Builder", "Elsaidy Builder"),
        ("en", "Builder", "Elsaidy Builder"),
        ("en", "Frappe Wiki", "Elsaidy Wiki"),
        ("en", "Wiki", "Elsaidy Wiki"),
        ("en", "Raven", "Elsaidy AI (Raven)"),
        ("en", "Hagag", "Elsaidy"),
        ("en", "Frappe", "Elsaidy")
    ]
    for lang, src, tr in trans_entries:
        existing = frappe.db.get_value("Translation", {"language": lang, "source_text": src}, "name")
        if existing:
            frappe.db.set_value("Translation", existing, "translated_text", tr)
        else:
            try:
                doc = frappe.new_doc("Translation")
                doc.language = lang
                doc.source_text = src
                doc.translated_text = tr
                doc.insert(ignore_permissions=True)
            except Exception:
                pass

    frappe.db.commit()


def sync_fcrm_and_helpdesk():
    """
    Configures Elsaidy CRM and Elsaidy Helpdesk settings, Saudi contracting deal stages, teams, and ticket types.
    """
    print("\n[Elsaidy ERP] Synchronizing Elsaidy CRM & Helpdesk...")
    logo_svg = "/assets/hagag_erp/images/elsaidy_logo.svg"

    if frappe.db.exists("DocType", "HD Settings"):
        try:
            hd = frappe.get_single("HD Settings")
            hd.brand_name = "Elsaidy Support - ركن سبل الأفق"
            hd.brand_logo = logo_svg
            hd.setup_complete = 1
            hd.initial_helpdesk_name_setup_skipped = 1
            hd.save(ignore_permissions=True)
        except Exception as e:
            print(f" -> Warning updating HD Settings: {e}")

    if frappe.db.exists("DocType", "FCRM Settings"):
        try:
            fcrm = frappe.get_single("FCRM Settings")
            fcrm.brand_name = "Elsaidy CRM"
            fcrm.brand_logo = logo_svg
            fcrm.setup_completed = 1
            for item in fcrm.dropdown_items:
                if "Hagag" in (item.label or ""):
                    item.label = item.label.replace("Hagag", "Elsaidy")
            fcrm.save(ignore_permissions=True)
        except Exception as e:
            print(f" -> Warning updating FCRM Settings: {e}")

    # CRM Lead Statuses
    lead_statuses = [
        {"lead_status": "فرصة جديدة / منصة اعتماد", "type": "Open", "color": "gray", "position": 1},
        {"lead_status": "شراء ودراسة كراسة الشروط", "type": "Ongoing", "color": "orange", "position": 2},
        {"lead_status": "حصر الكميات والتسعير الفني والمالي", "type": "Ongoing", "color": "blue", "position": 3},
        {"lead_status": "تقديم العرض الفني والمالي", "type": "Ongoing", "color": "yellow", "position": 4},
        {"lead_status": "مؤهل للمنافسة (Qualified)", "type": "Won", "color": "green", "position": 5},
        {"lead_status": "غير مطابق للشروط (Unqualified)", "type": "Lost", "color": "red", "position": 6}
    ]
    for ls in lead_statuses:
        name = ls["lead_status"]
        if not frappe.db.exists("CRM Lead Status", name):
            try:
                doc = frappe.new_doc("CRM Lead Status")
                doc.name = name
                doc.lead_status = name
                doc.type = ls["type"]
                doc.color = ls["color"]
                doc.position = ls["position"]
                doc.insert(ignore_permissions=True)
            except Exception:
                pass

    # CRM Deal Statuses
    deal_statuses = [
        {"deal_status": "فرصة جديدة / منصة اعتماد", "type": "Open", "color": "gray", "position": 1, "probability": 10},
        {"deal_status": "شراء ودراسة كراسة الشروط", "type": "Ongoing", "color": "orange", "position": 2, "probability": 25},
        {"deal_status": "حصر الكميات والتسعير الفني والمالي", "type": "Ongoing", "color": "blue", "position": 3, "probability": 50},
        {"deal_status": "تقديم العرض الفني والمالي", "type": "Ongoing", "color": "purple", "position": 4, "probability": 70},
        {"deal_status": "الترسية المبدئية والتفاوض", "type": "Ongoing", "color": "amber", "position": 5, "probability": 90},
        {"deal_status": "تم التعميد وتوقيع العقد (Won)", "type": "Won", "color": "green", "position": 6, "probability": 100},
        {"deal_status": "مغلق / لم يرسُ (Lost)", "type": "Lost", "color": "red", "position": 7, "probability": 0}
    ]
    for ds in deal_statuses:
        name = ds["deal_status"]
        if not frappe.db.exists("CRM Deal Status", name):
            try:
                doc = frappe.new_doc("CRM Deal Status")
                doc.name = name
                doc.deal_status = name
                doc.type = ds["type"]
                doc.color = ds["color"]
                doc.position = ds["position"]
                doc.probability = ds["probability"]
                doc.insert(ignore_permissions=True)
            except Exception:
                pass

    # HD Teams with mandatory users
    teams = ["الدعم التقني ونظام Elsaidy ERP", "إدارة المعدات والآليات الثقيلة", "دعم المشاريع والمواقع الميدانية"]
    for t in teams:
        if not frappe.db.exists("HD Team", t):
            try:
                doc = frappe.new_doc("HD Team")
                doc.name = t
                doc.team_name = t
                doc.disabled = 0
                doc.append("users", {"user": "Administrator"})
                doc.insert(ignore_permissions=True)
            except Exception:
                pass

    # HD Ticket Types
    ttypes = [
        ("عطل معدة أو آلية بالموقع", "بلاغات أعطال وصيانة المعدات والشاحنات في مواقع المشروعات"),
        ("طلب مواد أو مهمات عاجلة", "طلبات توريد وتشغيل المواد والمهمات الطارئة للمواقع"),
        ("ملاحظة سلامة وجودة ميدانية (HSE)", "تقارير السلامة المهنية وملاحظات ضبط الجودة بالمشاريع"),
        ("دعم تقني أو محاسبي", "طلبات الدعم الفني ونظام Elsaidy ERP والمحاسبة")
    ]
    for tname, tdesc in ttypes:
        if not frappe.db.exists("HD Ticket Type", tname):
            try:
                doc = frappe.new_doc("HD Ticket Type")
                doc.name = tname
                doc.description = tdesc
                doc.disabled = 0
                doc.insert(ignore_permissions=True)
            except Exception:
                pass

    frappe.db.commit()


def clean_raven_channels():
    """
    Removes redundant or typo channels so Raven only presents clean official channels.
    """
    print("\n[Elsaidy ERP] Cleaning Raven Channels...")
    for old_ch in ["raven-tsst", "raven-تيم-الشغل"]:
        if frappe.db.exists("Raven Channel", old_ch):
            try:
                frappe.delete_doc("Raven Channel", old_ch, force=1)
                print(f" -> Removed old channel: {old_ch}")
            except Exception as e:
                print(f" -> Warning deleting channel {old_ch}: {e}")
    frappe.db.commit()


def sync_saudi_custom_fields():
    """
    Ensures Custom Fields for IPC progress billing and Saudi compliance (GOSI, SVP) exist on Sales Invoice, Purchase Invoice, and Employee.
    """
    print("\n[Elsaidy ERP] Synchronizing Saudi Contracting Custom Fields...")
    ipc_fields = [
        {"fieldname": "custom_ipc_section", "label": "بيانات المستخلصات وضمان الأعمال (المقاولات)", "fieldtype": "Section Break", "insert_after": "taxes_section"},
        {"fieldname": "custom_ipc_type", "label": "نوع المستخلص / الفاتورة", "fieldtype": "Select", "options": "\nفاتورة ضريبية عادية\nدفعة مقدمة\nمستخلص جاري\nمستخلص ختامي", "default": "مستخلص جاري", "insert_after": "custom_ipc_section"},
        {"fieldname": "custom_ipc_number", "label": "رقم المستخلص", "fieldtype": "Data", "insert_after": "custom_ipc_type"},
        {"fieldname": "custom_contract_value", "label": "قيمة العقد الإجمالية (SAR)", "fieldtype": "Currency", "insert_after": "custom_ipc_number"},
        {"fieldname": "custom_previous_ipc_total", "label": "إجمالي المستخلصات السابقة (SAR)", "fieldtype": "Currency", "insert_after": "custom_contract_value"},
        {"fieldname": "custom_ipc_col_break", "label": None, "fieldtype": "Column Break", "insert_after": "custom_previous_ipc_total"},
        {"fieldname": "custom_advance_recovery_pct", "label": "نسبة استرداد الدفعة المقدمة %", "fieldtype": "Percent", "insert_after": "custom_ipc_col_break"},
        {"fieldname": "custom_advance_recovery_amount", "label": "مبلغ استرداد الدفعة المقدمة (SAR)", "fieldtype": "Currency", "insert_after": "custom_advance_recovery_pct"},
        {"fieldname": "custom_retention_pct", "label": "نسبة ضمان حسن التنفيذ (Retention) %", "fieldtype": "Percent", "default": "10.0", "insert_after": "custom_advance_recovery_amount"},
        {"fieldname": "custom_retention_amount", "label": "مبلغ محجوز ضمان الأعمال (Retention SAR)", "fieldtype": "Currency", "insert_after": "custom_retention_pct"}
    ]

    for dt in ["Sales Invoice", "Purchase Invoice"]:
        for f in ipc_fields:
            cf_name = f"{dt}-{f['fieldname']}"
            if not frappe.db.exists("Custom Field", cf_name):
                try:
                    cf = frappe.new_doc("Custom Field")
                    cf.name = cf_name
                    cf.dt = dt
                    cf.fieldname = f["fieldname"]
                    cf.label = f["label"]
                    cf.fieldtype = f["fieldtype"]
                    if f.get("options"):
                        cf.options = f["options"]
                    if f.get("default"):
                        cf.default = f["default"]
                    cf.insert_after = f.get("insert_after")
                    cf.insert(ignore_permissions=True)
                except Exception:
                    pass

    emp_fields = [
        {"fieldname": "custom_saudi_compliance_section", "label": "بيانات الإقامة والامتثال السعودي (GOSI & SVP)", "fieldtype": "Section Break", "insert_after": "employment_details_tab"},
        {"fieldname": "custom_iqama_number", "label": "رقم الإقامة / الهوية الوطنية", "fieldtype": "Data", "insert_after": "custom_saudi_compliance_section"},
        {"fieldname": "custom_iqama_expiry", "label": "تاريخ انتهاء الإقامة", "fieldtype": "Date", "insert_after": "custom_iqama_number"},
        {"fieldname": "custom_svp_certificate_no", "label": "رقم شهادة الفحص المهني (SVP)", "fieldtype": "Data", "insert_after": "custom_iqama_expiry"},
        {"fieldname": "custom_compliance_col_break", "label": None, "fieldtype": "Column Break", "insert_after": "custom_svp_certificate_no"},
        {"fieldname": "custom_medical_insurance_expiry", "label": "تاريخ انتهاء التأمين الطبي", "fieldtype": "Date", "insert_after": "custom_compliance_col_break"},
        {"fieldname": "custom_gosi_number", "label": "رقم المشترك في التأمينات (GOSI)", "fieldtype": "Data", "insert_after": "custom_medical_insurance_expiry"}
    ]
    for f in emp_fields:
        cf_name = f"Employee-{f['fieldname']}"
        if not frappe.db.exists("Custom Field", cf_name):
            try:
                cf = frappe.new_doc("Custom Field")
                cf.name = cf_name
                cf.dt = "Employee"
                cf.fieldname = f["fieldname"]
                cf.label = f["label"]
                cf.fieldtype = f["fieldtype"]
                if f.get("options"):
                    cf.options = f["options"]
                cf.insert_after = f.get("insert_after")
                cf.insert(ignore_permissions=True)
            except Exception:
                pass

    # ZATCA Tax & Idempotency Custom Fields for Journal Entry
    zatca_je_fields = [
        {"fieldname": "custom_zatca_section", "label": "بيانات الفحص الضريبي وهيئة الزكاة (ZATCA)", "fieldtype": "Section Break", "insert_after": "user_remark"},
        {"fieldname": "custom_tax_review_status", "label": "حالة التدقيق الضريبي", "fieldtype": "Select", "options": "\nمكتمل ومطابق\nقيد المراجعة الضريبية\nمستبعد من الاسترداد الضريبي\nغير خاضع للضريبة", "default": "مكتمل ومطابق", "insert_after": "custom_zatca_section"},
        {"fieldname": "custom_has_valid_tax_invoice", "label": "توفر فاتورة ضريبية نظامية", "fieldtype": "Check", "default": "1", "insert_after": "custom_tax_review_status"},
        {"fieldname": "custom_contract_type", "label": "نوع العقد التجاري", "fieldtype": "Select", "options": "\nعقد تجاري خاص\nعقد حكومي منصة اعتماد", "default": "عقد تجاري خاص", "insert_after": "custom_has_valid_tax_invoice"},
        {"fieldname": "custom_col_zatca", "label": None, "fieldtype": "Column Break", "insert_after": "custom_contract_type"},
        {"fieldname": "custom_operation_id", "label": "معرف العملية الموحد (Idempotency Key)", "fieldtype": "Data", "insert_after": "custom_col_zatca"},
        {"fieldname": "custom_ai_audit_trail", "label": "سجل تدقيق الذكاء الاصطناعي (AI Audit Trail)", "fieldtype": "Small Text", "insert_after": "custom_operation_id"}
    ]
    for f in zatca_je_fields:
        cf_name = f"Journal Entry-{f['fieldname']}"
        if not frappe.db.exists("Custom Field", cf_name):
            try:
                cf = frappe.new_doc("Custom Field")
                cf.name = cf_name
                cf.dt = "Journal Entry"
                cf.fieldname = f["fieldname"]
                cf.label = f["label"]
                cf.fieldtype = f["fieldtype"]
                if f.get("options"):
                    cf.options = f["options"]
                if f.get("default"):
                    cf.default = f["default"]
                cf.insert_after = f.get("insert_after")
                cf.insert(ignore_permissions=True)
            except Exception:
                pass

    # ZATCA Tax & Idempotency Custom Fields for Purchase Invoice & Sales Invoice
    zatca_inv_fields = [
        {"fieldname": "custom_tax_review_status", "label": "حالة التدقيق الضريبي", "fieldtype": "Select", "options": "\nمكتمل ومطابق\nقيد المراجعة الضريبية\nمستبعد من الاسترداد الضريبي\nغير خاضع للضريبة", "default": "مكتمل ومطابق", "insert_after": "custom_retention_amount"},
        {"fieldname": "custom_has_valid_tax_invoice", "label": "توفر فاتورة ضريبية نظامية", "fieldtype": "Check", "default": "1", "insert_after": "custom_tax_review_status"},
        {"fieldname": "custom_contract_type", "label": "نوع العقد التجاري", "fieldtype": "Select", "options": "\nعقد تجاري خاص\nعقد حكومي منصة اعتماد", "default": "عقد تجاري خاص", "insert_after": "custom_has_valid_tax_invoice"},
        {"fieldname": "custom_operation_id", "label": "معرف العملية الموحد (Idempotency Key)", "fieldtype": "Data", "insert_after": "custom_contract_type"},
        {"fieldname": "custom_ai_audit_trail", "label": "سجل تدقيق الذكاء الاصطناعي (AI Audit Trail)", "fieldtype": "Small Text", "insert_after": "custom_operation_id"}
    ]
    for dt in ["Purchase Invoice", "Sales Invoice"]:
        for f in zatca_inv_fields:
            cf_name = f"{dt}-{f['fieldname']}"
            if not frappe.db.exists("Custom Field", cf_name):
                try:
                    cf = frappe.new_doc("Custom Field")
                    cf.name = cf_name
                    cf.dt = dt
                    cf.fieldname = f["fieldname"]
                    cf.label = f["label"]
                    cf.fieldtype = f["fieldtype"]
                    if f.get("options"):
                        cf.options = f["options"]
                    if f.get("default"):
                        cf.default = f["default"]
                    cf.insert_after = f.get("insert_after")
                    cf.insert(ignore_permissions=True)
                except Exception:
                    pass

    frappe.db.commit()


def sync_insights_v3_dashboards():
    """
    Sets up the 2 official Executive Owner Dashboards in Frappe Insights v3 on Site DB.
    """
    print("\n[Elsaidy ERP] Synchronizing Insights v3 Executive Dashboards...")
    wb_name = "1"
    if frappe.db.exists("Insights Workbook", wb_name):
        frappe.db.set_value("Insights Workbook", wb_name, "title", "لوحة القيادة التنفيذية - Elsaidy ERP")
    else:
        wb = frappe.new_doc("Insights Workbook")
        wb.name = wb_name
        wb.title = "لوحة القيادة التنفيذية - Elsaidy ERP"
        wb.insert(ignore_permissions=True)

    # Delete sample Order Analysis dashboard
    if frappe.db.exists("Insights Dashboard v3", "7ejur6mapv"):
        try:
            frappe.delete_doc("Insights Dashboard v3", "7ejur6mapv", force=1)
        except Exception:
            pass

    queries_def = [
        {"key": "gl", "title": "حركات الأستاذ العام - Elsaidy GL", "table": "tabGL Entry"},
        {"key": "sales", "title": "فواتير ومستخلصات المبيعات - Sales Invoices", "table": "tabSales Invoice"},
        {"key": "accounts", "title": "شجرة الحسابات والأرصدة - Accounts", "table": "tabAccount"},
        {"key": "employees", "title": "بيانات الكوادر البشرية والموظفين - Employees", "table": "tabEmployee"},
        {"key": "projects", "title": "سجل المشروعات والمواقع - Projects", "table": "tabProject"}
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
        {"key": "table_detailed_ledger", "title": "سجل الحركات المالية التفصيلي حسب المشروع ومركز التكلفة", "query_key": "gl", "chart_type": "Table", "config": {"filters": {"filters": [], "logical_operator": "And"}, "limit": 50, "rows": [{"column_name": "posting_date", "data_type": "Date", "dimension_name": "posting_date", "label": "تاريخ الحركة", "value": "posting_date"}, {"column_name": "account", "data_type": "String", "dimension_name": "account", "label": "اسم الحساب", "value": "account"}, {"column_name": "project", "data_type": "String", "dimension_name": "project", "label": "المشروع", "value": "project"}], "columns": [], "values": [{"aggregation": "sum", "column_name": "debit", "data_type": "Decimal", "label": "مدين", "measure_name": "مدين"}, {"aggregation": "sum", "column_name": "credit", "data_type": "Decimal", "label": "دائن", "measure_name": "دائن"}]}}
    ]

    chart_map = {}
    for c in charts_def:
        existing = frappe.get_all("Insights Chart v3", filters={"workbook": wb_name, "title": c["title"]}, pluck="name")
        if existing:
            chart_map[c["key"]] = existing[0]
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

    # Dashboard 1
    d1_title = "لوحة المالك والمدير العام - الملخص التنفيذي الشامل"
    d1_items = [
        {"chart": chart_map["kpi_liquidity"], "type": "chart", "layout": {"h": 3, "i": "kpi1", "w": 5, "x": 0, "y": 0, "moved": False}},
        {"chart": chart_map["kpi_contracts"], "type": "chart", "layout": {"h": 3, "i": "kpi2", "w": 5, "x": 5, "y": 0, "moved": False}},
        {"chart": chart_map["kpi_expenses"], "type": "chart", "layout": {"h": 3, "i": "kpi3", "w": 5, "x": 10, "y": 0, "moved": False}},
        {"chart": chart_map["kpi_vat"], "type": "chart", "layout": {"h": 3, "i": "kpi4", "w": 5, "x": 15, "y": 0, "moved": False}},
        {"chart": chart_map["chart_expenses_donut"], "type": "chart", "layout": {"h": 8, "i": "v1", "w": 10, "x": 0, "y": 3, "moved": False}},
        {"chart": chart_map["chart_projects_bar"], "type": "chart", "layout": {"h": 8, "i": "v2", "w": 10, "x": 10, "y": 3, "moved": False}},
        {"chart": chart_map["chart_cashflow_line"], "type": "chart", "layout": {"h": 8, "i": "v3", "w": 10, "x": 0, "y": 11, "moved": False}},
        {"chart": chart_map["table_accounts_summary"], "type": "chart", "layout": {"h": 8, "i": "v4", "w": 10, "x": 10, "y": 11, "moved": False}}
    ]

    existing_d1 = frappe.get_all("Insights Dashboard v3", filters={"title": d1_title}, pluck="name")
    if existing_d1:
        d1 = frappe.get_doc("Insights Dashboard v3", existing_d1[0])
        d1.workbook = wb_name
        d1.is_public = 1
        d1.items = json.dumps(d1_items)
        d1.set("linked_charts", [])
        for item in d1_items:
            d1.append("linked_charts", {"chart": item["chart"]})
        d1.save(ignore_permissions=True)
    else:
        d1 = frappe.new_doc("Insights Dashboard v3")
        d1.title = d1_title
        d1.workbook = wb_name
        d1.is_public = 1
        d1.items = json.dumps(d1_items)
        for item in d1_items:
            d1.append("linked_charts", {"chart": item["chart"]})
        d1.insert(ignore_permissions=True)

    # Dashboard 2
    d2_title = "التقارير التفصيلية للمشاريع والعهد والزكاة والضريبة"
    d2_items = [
        {"chart": chart_map["chart_bank_custody_bar"], "type": "chart", "layout": {"h": 8, "i": "o1", "w": 10, "x": 0, "y": 0, "moved": False}},
        {"chart": chart_map["chart_vat_pie"], "type": "chart", "layout": {"h": 8, "i": "o2", "w": 10, "x": 10, "y": 0, "moved": False}},
        {"chart": chart_map["chart_hr_headcount"], "type": "chart", "layout": {"h": 8, "i": "o3", "w": 10, "x": 0, "y": 8, "moved": False}},
        {"chart": chart_map["table_detailed_ledger"], "type": "chart", "layout": {"h": 8, "i": "o4", "w": 10, "x": 10, "y": 8, "moved": False}}
    ]

    existing_d2 = frappe.get_all("Insights Dashboard v3", filters={"title": d2_title}, pluck="name")
    if existing_d2:
        d2 = frappe.get_doc("Insights Dashboard v3", existing_d2[0])
        d2.workbook = wb_name
        d2.is_public = 1
        d2.items = json.dumps(d2_items)
        d2.set("linked_charts", [])
        for item in d2_items:
            d2.append("linked_charts", {"chart": item["chart"]})
        d2.save(ignore_permissions=True)
    else:
        d2 = frappe.new_doc("Insights Dashboard v3")
        d2.title = d2_title
        d2.workbook = wb_name
        d2.is_public = 1
        d2.items = json.dumps(d2_items)
        for item in d2_items:
            d2.append("linked_charts", {"chart": item["chart"]})
        d2.insert(ignore_permissions=True)

    frappe.db.commit()


def sync_raven_patch():
    """
    Ensures Raven's agents_integration.py has the multi-turn & Jinja patch applied.
    """
    patch_file = os.path.join(os.path.dirname(__file__), "raven_patch.py")
    target_file = "/home/frappe/frappe-bench/apps/raven/raven/ai/agents_integration.py"
    if os.path.exists(patch_file) and os.path.exists(target_file):
        try:
            with open(patch_file, "r", encoding="utf-8") as f:
                content = f.read()
            with open(target_file, "w", encoding="utf-8") as f:
                f.write(content)
            print(" -> Synchronized Raven patch to live raven app.")
        except OSError as e:
            if getattr(e, "errno", None) == 30 or "Read-only" in str(e):
                print(" -> Raven patch is already active via docker host bind-mount.")
            else:
                print(f" -> Warning synchronizing Raven patch: {e}")
        except Exception as e:
            print(f" -> Warning synchronizing Raven patch: {e}")


def sanitize_database_test_data(force=False, confirmation_token=None):
    """

    # Process sanitization
    # Master data preserved
    STRICT SAFETY LOCK: Execution is strictly forbidden on production site 'erp.local'.
    """
    current_site = getattr(frappe.local, "site", "")
    if current_site in ["erp.local", "https://erp.elsaidy.org", "erp.elsaidy.org"]:
        frappe.throw(
            "🛑 خطأ أمان حرج: محاولة تشغيل دالة التطهير sanitize_database_test_data محظورة نهائياً وبشكل قطعي على بيئة الإنتاج erp.local لحماية البيانات المالية للمؤسسة!",
            frappe.PermissionError
        )

    if not force or confirmation_token != "CONFIRM_ERASE_TEST_DATA_ONLY":
        frappe.throw(
            "🛑 إذن مرفوض: يجب تمرير المعامل force=True و confirmation_token='CONFIRM_ERASE_TEST_DATA_ONLY' صراحة لتشغيل هذه العملية على بيئة الاختبار.",
            frappe.PermissionError
        )
    """

    # Process sanitization
    # Master data preserved
    """


    transaction_doctypes = [
        "Payment Ledger Entry",
        "Stock Ledger Entry",
        "GL Entry",
        "Repost Item Valuation",
        "Serial and Batch Bundle",
        "Payment Entry",
        "Journal Entry",
        "Expense Claim",
        "Delivery Note",
        "Sales Invoice",
        "Sales Order",
        "Quotation",
        "Purchase Receipt",
        "Purchase Invoice",
        "Purchase Order",
        "Material Request",
        "Stock Entry",
        "Leave Application",
        "CRM Lead",
        "CRM Deal",
        "CRM Organization",
        "CRM Call Log",
        "CRM Task",
        "FCRM Note",
        "HD Ticket"
    ]

    for dt in transaction_doctypes:
        if frappe.db.exists("DocType", dt):
            try:
                table = f"tab{dt}"
                frappe.db.sql(f"DELETE FROM `{table}`")
            except Exception as e:
                print(f" -> Warning deleting from {dt}: {e}")

    for ledger in ["tabGL Entry", "tabStock Ledger Entry", "tabPayment Ledger Entry"]:
        try:
            frappe.db.sql(f"TRUNCATE `{ledger}`")
        except Exception:
            pass

    series_prefixes = [
        "ACC-JV-%", "SINV-%", "SO-%", "DN-%", "QTN-%",
        "PINV-%", "PO-%", "PREC-%", "MAT-REQ-%", "MAT-STE-%",
        "ACC-PAY-%", "HR-EXP-%", "HR-LAP-%", "CRM-LEAD-%", "CRM-DEAL-%", "HD-TKT-%"
    ]
    for prefix in series_prefixes:
        frappe.db.sql("DELETE FROM `tabSeries` WHERE `name` LIKE %s", prefix)

    for log_table in ["tabActivity Log", "tabError Log"]:
        try:
            frappe.db.sql(f"TRUNCATE `{log_table}`")
        except Exception:
            pass

    frappe.db.commit()
    print("[Elsaidy ERP] Zero transactions remain. Database is 100% clean for production!")


def sync_saudi_hr_preset():
    """
    Synchronizes Saudi Frappe HR & Payroll presets.
    """
    print("\n[Elsaidy ERP] Synchronizing Saudi HR & Payroll Preset...")
    comp = "شركة ركن سبل الأفق للمقاولات"
    abbr = "Rkn"

    salary_components = [
        {"salary_component": "الراتب الأساسي (Basic)", "type": "Earning", "description": "الراتب الأساسي وفق عقد العمل السعودي"},
        {"salary_component": "بدل سكن (Housing Allowance 25%)", "type": "Earning", "description": "بدل سكن يعادل 25% من الراتب الأساسي"},
        {"salary_component": "بدل نقل ومواصلات (Transport Allowance 10%)", "type": "Earning", "description": "بدل مواصلات وانتقال 10%"},
        {"salary_component": "بدل موقع ومشروع (Site Allowance)", "type": "Earning", "description": "بدل طبيعة عمل في المواقع الإنشائية"},
        {"salary_component": "أجر ساعات إضافية (Overtime)", "type": "Earning", "description": "ساعات العمل الإضافية المعتمدة"},
        {"salary_component": "تأمينات اجتماعية - حصة الموظف السعودي (GOSI 9.75%)", "type": "Deduction", "description": "استقطاع التأمينات الاجتماعية (حصة المشترك)"},
        {"salary_component": "استقطاع سلف وعهد رواتب (Advance Deduction)", "type": "Deduction", "description": "استقطاع أقساط السلف والعهد النقدية"},
        {"salary_component": "خصومات وجزاءات إدارية (Penalties)", "type": "Deduction", "description": "خصومات التأخير والجزاءات المعتمدة"},
        {"salary_component": "أخطار مهنية - غير سعودي (GOSI 2%)", "type": "Deduction", "description": "نسبة التأمين ضد الأخطار المهنية لغير السعوديين"}
    ]
    for sc in salary_components:
        name = sc["salary_component"]
        if not frappe.db.exists("Salary Component", name):
            try:
                doc = frappe.new_doc("Salary Component")
                doc.salary_component = name
                doc.salary_component_abbr = name[:10]
                doc.type = sc["type"]
                doc.description = sc["description"]
                doc.insert(ignore_permissions=True)
            except Exception:
                pass

    leave_types = [
        {"leave_type_name": "إجازة سنوية اعتيادية (Annual Leave)", "max_days_allowed": 21},
        {"leave_type_name": "إجازة مرضية (Sick Leave)", "max_days_allowed": 120},
        {"leave_type_name": "إجازة زواج (Marriage Leave)", "max_days_allowed": 5},
        {"leave_type_name": "إجازة وفاة (Bereavement Leave)", "max_days_allowed": 5},
        {"leave_type_name": "إجازة مولود (Paternity Leave)", "max_days_allowed": 3},
        {"leave_type_name": "إجازة أداء فريضة الحج (Hajj Leave)", "max_days_allowed": 10},
        {"leave_type_name": "إجازة بدون راتب (Unpaid Leave)", "max_days_allowed": 0}
    ]
    for lt in leave_types:
        name = lt["leave_type_name"]
        if not frappe.db.exists("Leave Type", name):
            try:
                doc = frappe.new_doc("Leave Type")
                doc.leave_type_name = name
                doc.max_days_allowed = lt["max_days_allowed"]
                doc.insert(ignore_permissions=True)
            except Exception:
                pass

    departments = [
        f"الإدارة العامة - {abbr}",
        f"الإدارة المالية والمحاسبية - {abbr}",
        f"إدارة المشاريع والتنفيذ - {abbr}",
        f"إدارة المشتريات والمستودعات - {abbr}",
        f"إدارة الموارد البشرية والشؤون الإدارية - {abbr}",
        f"إدارة السلامة والجودة (HSE & QC) - {abbr}"
    ]
    for dept in departments:
        if not frappe.db.exists("Department", dept):
            try:
                doc = frappe.new_doc("Department")
                doc.department_name = dept
                doc.company = comp
                doc.insert(ignore_permissions=True)
            except Exception:
                pass

    designations = [
        "مدير عام / تنفيذي",
        "مدير مشاريع",
        "مهندس موقع مدني",
        "مهندس كهرباء / ميكانيكا",
        "محاسب عام ومستخلصات",
        "مسؤول مشتريات ومستودع",
        "مشرف سلامة وصحة مهنية (HSE)",
        "مساح أراضي عام",
        "مشرف عمال ومعدات"
    ]
    for des in designations:
        if not frappe.db.exists("Designation", des):
            try:
                doc = frappe.new_doc("Designation")
                doc.designation_name = des
                doc.insert(ignore_permissions=True)
            except Exception:
                pass

    expense_types = [
        "عهدة مشتريات موقع فورية",
        "وقود ومحروقات سيارات ومعدات",
        "إعاشة وضيافة مواقع ومشروعات",
        "صيانة وقطع غيار طارئة بالموقع",
        "رسوم وتراخيص ونثريات إدارية"
    ]
    for et in expense_types:
        if not frappe.db.exists("Expense Claim Type", et):
            try:
                doc = frappe.new_doc("Expense Claim Type")
                doc.expense_type = et
                doc.insert(ignore_permissions=True)
            except Exception:
                pass

    frappe.db.commit()


def sync_saudi_crm_preset():
    """
    Synchronizes Saudi Contracting CRM territories, customer/supplier groups, and sales stages.
    """
    print("\n[Elsaidy ERP] Synchronizing Saudi CRM & Selling Preset...")
    sa_root = "المملكة العربية السعودية"
    if not frappe.db.exists("Territory", sa_root):
        try:
            doc = frappe.new_doc("Territory")
            doc.territory_name = sa_root
            doc.is_group = 1
            doc.insert(ignore_permissions=True)
        except Exception:
            pass

    regions = ["الرياض", "شقراء وساجر", "المنطقة الوسطى", "المنطقة الشرقية", "المنطقة الغربية"]
    for reg in regions:
        if not frappe.db.exists("Territory", reg):
            try:
                doc = frappe.new_doc("Territory")
                doc.territory_name = reg
                doc.parent_territory = sa_root
                doc.is_group = 0
                doc.insert(ignore_permissions=True)
            except Exception:
                pass

    cust_groups = ["جهات حكومية ووزارات", "شركات تطوير عقاري", "مقاولون رئيسيون", "قطاع خاص وأفراد"]
    for cg in cust_groups:
        if not frappe.db.exists("Customer Group", cg):
            try:
                doc = frappe.new_doc("Customer Group")
                doc.customer_group_name = cg
                doc.is_group = 0
                doc.insert(ignore_permissions=True)
            except Exception:
                pass

    supp_groups = ["مقاولو باطن - أعمال مدنية", "موردو مواد بناء وخرسانة", "شركات تأجير آليات ثقيلة", "موردو محروقات وخدمات تشغيل"]
    for sg in supp_groups:
        if not frappe.db.exists("Supplier Group", sg):
            try:
                doc = frappe.new_doc("Supplier Group")
                doc.supplier_group_name = sg
                doc.is_group = 0
                doc.insert(ignore_permissions=True)
            except Exception:
                pass

    frappe.db.commit()


def sync_elsaidy_dashboards():
    """
    Creates executive visual Number Cards and standard Dashboards for Elsaidy ERP.
    """
    print("\n[Elsaidy ERP] Synchronizing Executive Dashboards & Number Cards...")
    cards = [
        {
            "name": "إجمالي السيولة النقدية والبنكية",
            "label": "إجمالي السيولة النقدية والبنكية",
            "document_type": "GL Entry",
            "function": "Sum",
            "aggregate_function_based_on": "debit",
            "filters_json": '[["GL Entry", "account", "in", ["1110 - النقدية في الصندوق - Rkn", "1120 - عهد نقدية للمهندسين والمشرفين - Rkn"]], ["GL Entry", "is_cancelled", "=", 0]]'
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
            except Exception:
                pass
    frappe.db.commit()


def sync_elsaidy_customizations():
    """
    Main idempotent synchronization function called on after_migrate.
    Ensures Elsaidy branding, Raven AI Functions, Bot configurations, Channels,
    Document Notifications, Message Actions, Saudi Accounting, HR, CRM presets,
    Executive Dashboards, and White-Labeling are permanently applied.
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
            print(" -> Raven Settings configured.")
    except Exception as e:
        print(f" -> Warning updating Raven Settings: {e}")

    # 2. 100% White-Labeling & Branding
    try:
        sync_whitelabel_and_branding()
    except Exception as e:
        print(f" -> Error in sync_whitelabel_and_branding: {e}")

    # 3. Desktop Icons & Translations
    try:
        sync_desktop_icons_and_translations()
    except Exception as e:
        print(f" -> Error in sync_desktop_icons_and_translations: {e}")

    # 4. FCRM & Helpdesk Setup
    try:
        sync_fcrm_and_helpdesk()
    except Exception as e:
        print(f" -> Error in sync_fcrm_and_helpdesk: {e}")

    # 5. Clean Raven Channels
    try:
        clean_raven_channels()
    except Exception as e:
        print(f" -> Error in clean_raven_channels: {e}")

    # 6. Saudi Custom Fields (IPC & Compliance)
    try:
        sync_saudi_custom_fields()
    except Exception as e:
        print(f" -> Error in sync_saudi_custom_fields: {e}")

    # 7. Register or Update Raven AI Functions
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

    # 8. Configure Raven Bots
    for bot_name, cfg in BOT_CONFIGS.items():
        try:
            if not frappe.db.exists("Raven Bot", bot_name):
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

            bot_doc.set("bot_functions", [])
            for fn in cfg["functions"]:
                if frappe.db.exists("Raven AI Function", fn):
                    bot_doc.append("bot_functions", {"function": fn})

            bot_doc.save(ignore_permissions=True)
            frappe.db.commit()
            print(f" -> Configured Bot '{bot_name}' with {len(bot_doc.bot_functions)} functions.")
        except Exception as e:
            print(f" -> Error configuring bot '{bot_name}': {e}")

    # 9. Configure Raven Channels & Memberships
    system_members = ["Administrator", "alyahmedelseidy@gmail.com"]
    for ch_cfg in CHANNELS_CONFIG:
        try:
            ch_id = ch_cfg["channel_id"]
            if not frappe.db.exists("Raven Channel", ch_id):
                doc = frappe.get_doc({
                    "doctype": "Raven Channel",
                    "name": ch_id,
                    "channel_name": ch_cfg["channel_name"],
                    "channel_description": ch_cfg["description"],
                    "type": ch_cfg["type"],
                    "workspace": "Raven"
                })
                doc.insert(ignore_permissions=True)
                print(f" -> Created channel: {ch_cfg['channel_name']} ({ch_id})")
            doc = frappe.get_doc("Raven Channel", ch_id)
            doc.channel_description = ch_cfg["description"]
            doc.workspace = "Raven"
            doc.save(ignore_permissions=True)

            for user_email in system_members:
                if frappe.db.exists("Raven User", user_email):
                    if not frappe.db.exists("Raven Channel Member", {"channel_id": ch_id, "user_id": user_email}):
                        cm = frappe.new_doc("Raven Channel Member")
                        cm.channel_id = ch_id
                        cm.user_id = user_email
                        cm.is_admin = 1
                        cm.insert(ignore_permissions=True)

            bot_name = ch_cfg.get("bot")
            if bot_name and frappe.db.exists("Raven User", bot_name):
                if not frappe.db.exists("Raven Channel Member", {"channel_id": ch_id, "user_id": bot_name}):
                    cm = frappe.new_doc("Raven Channel Member")
                    cm.channel_id = ch_id
                    cm.user_id = bot_name
                    cm.is_admin = 0
                    cm.insert(ignore_permissions=True)

            print(f" -> Configured channel: {ch_cfg['channel_name']} ({ch_id})")
            frappe.db.commit()
        except Exception as e:
            print(f" -> Error configuring channel {ch_cfg['channel_name']}: {e}")

    # 10. Configure Document Notifications
    for notif in DOCUMENT_NOTIFICATIONS:
        try:
            n_name = notif["name"]
            if not frappe.db.exists("Raven Document Notification", n_name):
                doc = frappe.get_doc({
                    "doctype": "Raven Document Notification",
                    "notification_name": n_name,
                    "document_type": notif["document_type"],
                    "event": notif["event"],
                    "send_to": "Channel",
                    "channel": notif["channel"],
                    "template": notif["template"],
                    "is_active": 1
                })
                doc.insert(ignore_permissions=True)
                print(f" -> Configured Document Notification: {n_name}")
            else:
                doc = frappe.get_doc("Raven Document Notification", n_name)
                doc.template = notif["template"]
                doc.channel = notif["channel"]
                doc.is_active = 1
                doc.save(ignore_permissions=True)
            frappe.db.commit()
        except Exception as e:
            print(f" -> Error configuring Notification {notif['name']}: {e}")

    # 11. Configure Message Actions
    for act in MESSAGE_ACTIONS:
        try:
            a_name = act["action_name"]
            existing = frappe.get_all("Raven Message Action", filters={"action_name": a_name}, fields=["name"])
            if existing:
                doc = frappe.get_doc("Raven Message Action", existing[0].name)
                doc.action = "Create Document"
                doc.document_type = act.get("target_doctype") or act.get("document_type")
                doc.title = act.get("title") or a_name
                doc.description = act["description"]
                doc.enabled = 1
                doc.save(ignore_permissions=True)
                for extra in existing[1:]:
                    frappe.delete_doc("Raven Message Action", extra.name, ignore_permissions=True)
                print(f" -> Updated Message Action: {a_name}")
            else:
                doc = frappe.new_doc("Raven Message Action")
                doc.action_name = a_name
                doc.title = act.get("title") or a_name
                doc.action = "Create Document"
                doc.document_type = act.get("target_doctype") or act.get("document_type")
                doc.description = act["description"]
                doc.enabled = 1
                doc.insert(ignore_permissions=True)
                print(f" -> Created Message Action: {a_name}")
            frappe.db.commit()
        except Exception as e:
            print(f" -> Error configuring Message Action {act.get('action_name')}: {e}")

    # 12. Scheduler Event
    try:
        event_name = "Daily Morning Briefing"
        if not frappe.db.exists("Raven Scheduler Event", event_name):
            se = frappe.new_doc("Raven Scheduler Event")
            se.event_name = event_name
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
        else:
            se = frappe.get_doc("Raven Scheduler Event", event_name)
            se.event_frequency = "Cron"
            se.cron_expression = "0 9 * * *"
            se.save(ignore_permissions=True)
            frappe.db.commit()
    except Exception as e:
        print(f" -> Warning configuring Scheduler Event: {e}")

    # 13. Synchronize Saudi Contracting & ZATCA Accounting Preset
    try:
        sync_saudi_accounting_preset()
    except Exception as e:
        print(f" -> Error in sync_saudi_accounting_preset: {e}")

    # 14. Synchronize Saudi Print Formats (Invoice & IPC)
    try:
        sync_saudi_print_formats()
    except Exception as e:
        print(f" -> Error in sync_saudi_print_formats: {e}")

    # 15. Synchronize Saudi HR & Payroll Preset
    try:
        sync_saudi_hr_preset()
    except Exception as e:
        print(f" -> Error in sync_saudi_hr_preset: {e}")

    # 16. Synchronize Saudi CRM & Selling Preset
    try:
        sync_saudi_crm_preset()
    except Exception as e:
        print(f" -> Error in sync_saudi_crm_preset: {e}")

    # 17. Synchronize Standard Number Cards & Dashboards
    try:
        sync_elsaidy_dashboards()
    except Exception as e:
        print(f" -> Error in sync_elsaidy_dashboards: {e}")

    # 18. Synchronize Insights v3 Executive Dashboards
    try:
        sync_insights_v3_dashboards()
    except Exception as e:
        print(f" -> Error in sync_insights_v3_dashboards: {e}")

    # 19. Synchronize Raven Patch
    try:
        sync_raven_patch()
    except Exception as e:
        print(f" -> Warning in sync_raven_patch: {e}")

    print("\n[Elsaidy ERP] All customizations synchronized successfully!\n")
    return True


@frappe.whitelist()
def cleanup_test_draft():
    """Safely cleans up only the unapproved test draft ACC-JV-2026-00001 and resets the naming series counter."""
    if frappe.db.exists("Journal Entry", "ACC-JV-2026-00001"):
        doc = frappe.get_doc("Journal Entry", "ACC-JV-2026-00001")
        if doc.docstatus == 0:
            doc.delete(ignore_permissions=True)
            print("Deleted test draft ACC-JV-2026-00001 successfully.")
        else:
            print(f"ACC-JV-2026-00001 has docstatus={doc.docstatus}, preserved.")
    else:
        print("ACC-JV-2026-00001 does not exist.")

    frappe.db.sql("UPDATE tabSeries SET current = 0 WHERE name = 'ACC-JV-2026-'")
    frappe.db.commit()
    print("Series counter for ACC-JV-2026- reset to 0 successfully.")

