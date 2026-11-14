import frappe
import json

def update_raven_governance():
    print("=== Updating Raven AI Functions & Bot Governance ===")
    
    # 1. Register prepare_financial_operation_preview
    f1_name = "prepare_financial_operation_preview"
    if not frappe.db.exists("Raven AI Function", f1_name):
        f1 = frappe.new_doc("Raven AI Function")
        f1.name = f1_name
        f1.function_name = f1_name
        f1.type = "Custom Function"
        f1.function_path = "hagag_erp.ai_tools.prepare_financial_operation_preview"
        f1.description = "يعد معاينة مالية ومحاسبية دقيقة لأي عملية (مصروف عهدة، صرف عهدة، سلفة) ويولد معرّف عملية OP-PREV. لا ينشئ أي قيد في النظام."
        f1.params = json.dumps({
            "type": "object",
            "properties": {
                "operation_type": {"type": "string", "enum": ["custody_expense", "custody_disbursement", "salary_advance"], "description": "نوع المعاملة"},
                "amount": {"type": "number", "description": "المبلغ الإجمالي بالريال"},
                "employee": {"type": "string", "description": "الموظف أو رقمه HR-EMP-00001"},
                "tax_status": {"type": "string", "enum": ["inclusive", "exclusive", "no_tax", "unspecified"], "description": "هل المبلغ شامل الضريبة 15% أم غير شامل"},
                "has_tax_invoice": {"type": "integer", "enum": [0, 1], "description": "1 إذا كانت تتوفر فاتورة ضريبية نظامية، 0 إن لم تتوفر"},
                "expense_category": {"type": "string", "description": "نوع المصروف مثل fuel أو maintenance"},
                "description": {"type": "string", "description": "بيان المصروف"}
            },
            "required": ["operation_type", "amount"]
        }, ensure_ascii=False)
        f1.insert(ignore_permissions=True)
        print(f"Created Raven AI Function: {f1_name}")
    else:
        frappe.db.set_value("Raven AI Function", f1_name, {
            "type": "Custom Function",
            "function_path": "hagag_erp.ai_tools.prepare_financial_operation_preview",
            "description": "يعد معاينة مالية ومحاسبية دقيقة لأي عملية (مصروف عهدة، صرف عهدة، سلفة) ويولد معرّف عملية OP-PREV. لا ينشئ أي قيد في النظام."
        })
        print(f"Updated Raven AI Function: {f1_name}")

    # 2. Register execute_confirmed_financial_operation
    f2_name = "execute_confirmed_financial_operation"
    if not frappe.db.exists("Raven AI Function", f2_name):
        f2 = frappe.new_doc("Raven AI Function")
        f2.name = f2_name
        f2.function_name = f2_name
        f2.type = "Custom Function"
        f2.function_path = "hagag_erp.ai_tools.execute_confirmed_financial_operation"
        f2.description = "ينفذ العملية المالية المحاسبية المؤكدة والمعلقة في النظام وينشئ القيد الفعلي ويتحقق من ترحيله بالأستاذ العام (docstatus=1)."
        f2.params = json.dumps({
            "type": "object",
            "properties": {
                "operation_id": {"type": "string", "description": "معرف العملية المعلقة مثل OP-PREV-XXXX"},
                "submit": {"type": "integer", "enum": [0, 1], "description": "1 لاعتماد القيد فوراً (موصى به)، 0 للإبقاء كمسودة"}
            }
        }, ensure_ascii=False)
        f2.insert(ignore_permissions=True)
        print(f"Created Raven AI Function: {f2_name}")
    else:
        frappe.db.set_value("Raven AI Function", f2_name, {
            "type": "Custom Function",
            "function_path": "hagag_erp.ai_tools.execute_confirmed_financial_operation",
            "description": "ينفذ العملية المالية المحاسبية المؤكدة والمعلقة في النظام وينشئ القيد الفعلي ويتحقق من ترحيله بالأستاذ العام (docstatus=1)."
        })
        print(f"Updated Raven AI Function: {f2_name}")

    # 3. Register submit_financial_document
    f3_name = "submit_financial_document"
    if not frappe.db.exists("Raven AI Function", f3_name):
        f3 = frappe.new_doc("Raven AI Function")
        f3.name = f3_name
        f3.function_name = f3_name
        f3.type = "Custom Function"
        f3.function_path = "hagag_erp.ai_tools.submit_financial_document"
        f3.description = "يعتمد ويرحل مستند مالي مسودة موجود فعلياً في ERPNext ويتحقق من docstatus=1 ويرسل إشعار الواتساب."
        f3.params = json.dumps({
            "type": "object",
            "properties": {
                "doctype": {"type": "string", "description": "نوع المستند مثل Journal Entry"},
                "document_name": {"type": "string", "description": "رقم المستند مثل ACC-JV-2026-00014"}
            },
            "required": ["doctype", "document_name"]
        }, ensure_ascii=False)
        f3.insert(ignore_permissions=True)
        print(f"Created Raven AI Function: {f3_name}")
    else:
        frappe.db.set_value("Raven AI Function", f3_name, {
            "type": "Custom Function",
            "function_path": "hagag_erp.ai_tools.submit_financial_document",
            "description": "يعتمد ويرحل مستند مالي مسودة موجود فعلياً في ERPNext ويتحقق من docstatus=1 ويرسل إشعار الواتساب."
        })
        print(f"Updated Raven AI Function: {f3_name}")

    # 4. Attach new functions to Raven Bot Accounting
    bot = frappe.get_doc("Raven Bot", "Accounting")
    existing_funcs = [bf.function for bf in bot.bot_functions]
    for fn in [f1_name, f2_name, f3_name]:
        if fn not in existing_funcs:
            bot.append("bot_functions", {"function": fn})
            print(f"Attached {fn} to Accounting bot")

    # 5. Clean and harden Accounting Bot Instruction
    clean_instruction = """أنت المدير المالي والمحاسبي الأول (Senior Financial & ERP Controller) لنظام Elsaidy ERP في شركة ركن سبل الأفق للمقاولات.

سياق النظام المالي الحي:
- الشركة: {{ company }}
- العملة المعتمدة: ريال سعودي (SAR)
- المستخدم: {{ user }}

قواعد الحوكمة والتنفيذ المالي الصارمة:
1. الالتزام القطعي باستدعاء الدوال المحاسبية (MANDATORY FUNCTION CALLING):
- أنت متصل بقاعدة بيانات ERPNext الحية عبر Function Tools.
- يُمنع منعاً باتاً إعلان إنشاء قيد أو مستند أو اعتماد معاملة مالية ما لم تقم باستدعاء الأداة المعتمدة وتستلم رداً بنجاح العملية (success = true) متضمناً رقم القيد ورابطه الحقيقي.
- يُمنع منعاً باتاً اختلاق أو تخمين أرقام مستندات (مثل ACC-JV-2026-00006) أو روابط وهمية.

2. منع الافتراض التلقائي لضريبة القيمة المضافة (ZERO TAX ASSUMPTION):
- يُمنع منعاً باتاً افتراض أن مبلغ الفاتورة يشمل ضريبة القيمة المضافة 15% تلقائياً دون تصريح صريح من المستخدم.
- عند طلب تسجيل أي مصروف، تحقق من:
  * هل المبلغ شامل الضريبة أم غير شامل؟
  * هل تتوفر فاتورة ضريبية نظامية للمعدات/السيارات التشغيلية وفق المادة 50 الزكوية؟
- إذا كانت هذه البيانات غير محددة، اسأل المستخدم فوراً واستدعِ prepare_financial_operation_preview لطلب الإيضاح قبل إنشاء أي قيد.

3. دورة المعاينة والتأكيد المحاسبي (Preview & Confirmation Workflow):
- عند طلب تسجيل أي مصروف عهدة أو صرف عهدة:
  1. استدعِ أداة prepare_financial_operation_preview لإظهار المعاينة المحاسبية (Dry Run) وتوليد معرّف العملية (OP-PREV).
  2. اعرض تفاصيل القيد والأثر المالي على الرصيد، واطلب تأكيد المستخدم.
  3. عند رد المستخدم بـ (أكد) أو (اعتمد) أو (موافق)، استدعِ execute_confirmed_financial_operation لتنفيذ القيد وترحيله فوراً.
  4. عند طلب اعتماد مستند مسودة موجود، استدعِ submit_financial_document.

4. الاستعلام الدفتري الحقيقي عن الأرصدة (Live GL Balance Inquiries):
- عند سؤال المستخدم عن رصيد العهدة أو كشف الحساب، استدعِ فوراً get_employee_custody_report أو get_gl_balance.
- يُمنع منعاً باتاً تخمين الرصيد أو كتابة 0.00 دون استدعاء الأداة.
- رصيد العهدة المعتمد يؤخذ حصراً من قيود الأستاذ العام (tabGL Entry) المسجلة على حساب 1120 بربط الموظف (Party Type = Employee).

5. التنسيق العربي الأنيق (RTL & Professional Tone):
- استخدم لغة عربية محاسبية رصينة ونقاطاً منظمة بالرموز التعبيرية الواضحة.
- ضع رابط المستند الرسمي دائماً على سطر مستقل بمفرده."""

    bot.instruction = clean_instruction
    bot.dynamic_instructions = 1
    bot.save(ignore_permissions=True)
    frappe.db.commit()
    print("Accounting Bot instruction updated and committed successfully!")

if __name__ == "__main__":
    update_raven_governance()
