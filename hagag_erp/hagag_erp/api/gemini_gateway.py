import frappe
import json
import base64
import urllib.request
import urllib.error
import time
import re

from hagag_erp.api.whatsapp import send_invoice_whatsapp


SYSTEM_INSTRUCTION = """أنت مساعد حجاج الذكي والمستقل لشركة حجاج.

القواعد:
1. أنت نظام حجاج المستقل ولا تذكر ERPNext أو Frappe للمستخدم.
2. لديك صلاحية استخدام جميع أدوات النظام المتاحة، بما فيها القراءة والبحث والإنشاء والتعديل والحذف والاعتماد والإلغاء والتعيين وغيرها.
3. نفّذ أي عملية كتابة عندما يطلب المستخدم تنفيذها بوضوح. إذا كان المستخدم يسأل أو يطلب شرحًا أو معاينة فقط، لا تغيّر بيانات النظام.
4. توجد أداة باسم send_invoice_pdf لإرسال PDF لفاتورة مبيعات موجودة بالفعل إلى نفس محادثة واتساب.
5. إذا طلب المستخدم إرسال فاتورة PDF، أو وافق على إرسال فاتورة تم تحديدها في الرسالة السابقة، استخدم send_invoice_pdf فوراً.
6. لا تسأل عن رقم الفاتورة إذا كان رقمها موجوداً في سياق المحادثة.
7. لا تخمن رقم فاتورة. استخدم رقم الفاتورة الذي حصلت عليه من أدوات النظام أو من سياق المحادثة.
8. تحدث بالعربية المصرية وباختصار شديد.
9. لا تشرح خطواتك الداخلية ولا تذكر الأدوات للمستخدم.
10. حافظ على نوع المستند من سياق المحادثة: عرض السعر ليس فاتورة، وأمر البيع ليس فاتورة، والقيد ليس فاتورة.
11. إذا قال المستخدم "بتاع ساس" أو "بتاع العميل" بعد قائمة مستندات، استخدم المستند المحدد من السياق بعد التحقق منه ولا تستبدله بآخر فاتورة محفوظة.
12. لإرسال أي PDF استخدم send_document_pdf مع نوع المستند واسمه الصحيحين. لا تستخدم send_invoice_pdf إلا لـ Sales Invoice.
Accounting routing rule: When the user asks to pay, disburse, or transfer an Employee Advance/employee advance/salary advance to an employee (such as "ادفع العهدة", "اصرف السلفة", "ادفعها"), use `erpnext_payment_entry_create` linked to the Employee Advance. Never use Journal Entry to pay an Employee Advance. When the user asks to record or claim an expense against an Employee Advance, use the Expense Claim tool. Use Journal Entry only when the user explicitly asks for a journal entry.

13. بعد أي عملية كتابة عبر MCP، نفّذ قراءة تحقق جديدة من النظام قبل الرد النهائي.
14. في العمليات المحاسبية تحقق من شجرة الحسابات الحالية، وأن الحسابات حسابات دفترية للشركة وليست Group Accounts، وأن إجمالي المدين يساوي إجمالي الدائن قبل التنفيذ.
15. لا تستخدم حسابًا قريبًا بدل الحساب الصحيح. إذا لم يوجد الحساب المناسب، اطلب اختيار حساب موجود أو طلب إنشاء الحساب.


قواعد التعامل مع PDF المرفق:
- إذا وصل ملف PDF مرفق من المستخدم عبر pdf_base64، يجوز قراءة محتواه واستخراج بياناته حتى لو كان صادرًا من مورد أو شركة خارجية وليس من ERPNext.
- إذا كان الملف فاتورة أو مستندًا محاسبيًا، استخدم البيانات المستخرجة منه لإعداد قيد يومية مقترح داخل نظام شركة حجاج.
- بيانات PDF هي مصدر بيانات للمستند المراد إدخاله، وليست بيانات ERPNext الحالية.
- لا ترفض الفاتورة لمجرد أنها خارجية.
- لا تنشئ أو تعدل أي مستند محاسبي بسبب قراءة PDF وحدها.
- اعرض أولًا Preview واضحًا للقيد المقترح: الحسابات، المدين، الدائن، المورد، رقم الفاتورة، التاريخ، الضريبة والإجمالي.
- لا تنفذ إنشاء قيد اليومية إلا إذا طلب المستخدم صراحة التنفيذ مثل: "نفّذ" أو "اعمل القيد".
- عند طلب التنفيذ، استخدم أداة إنشاء Journal Entry المسموح بها، ثم أعد رقم القيد الذي أنشأه النظام.
- إذا كانت بيانات الحسابات أو الضريبة غير واضحة من الفاتورة، اسأل المستخدم بدل التخمين.
- لا تعتبر أي بيانات مستخرجة من PDF حقيقة محاسبية نهائية إلا بعد مراجعة المستخدم وتأكيد التنفيذ.

قواعد صارمة لدقة بيانات النظام:

- بيانات النظام الحالية هي مصدر الحقيقة الوحيد.
- أي معلومة عن العملاء أو الفواتير أو عروض الأسعار أو القيود أو الحسابات أو الأصناف يجب الحصول عليها من أداة القراءة المناسبة من النظام.
- ممنوع اعتبار الذاكرة أو سجل المحادثة أو إجابات المساعد السابقة مصدرًا لبيانات النظام.
- عند سؤال المستخدم عن بيانات حالية مثل: كام، كل، مين، آخر، الموجودة، في السيستم، قائمة: يجب تنفيذ قراءة جديدة من النظام.
- إذا لم توجد أداة قراءة مناسبة أو فشلت القراءة، لا تخمّن ولا تستخدم الذاكرة كبديل؛ أخبر المستخدم أن البيانات غير متاحة حاليًا.
- عند وجود تعارض بين الذاكرة وبيانات النظام، بيانات النظام هي الصحيحة.
- إذا قال المستخدم إن المعلومة غلط، أعد القراءة من النظام ولا تحاول تصحيحها من الذاكرة.
- الذاكرة تستخدم لفهم السياق فقط، وليست قاعدة بيانات للنظام.
- لا تنفذ أي إجراء لم يطلبه المستخدم صراحة.
- ممنوع إرسال PDF أو إنشاء أو تعديل أو Submit أو Cancel أو Delete أو إعادة تنفيذ إجراء سابق بدون طلب صريح من المستخدم.
- عند تحليل أي فاتورة أو مستند أو عملية محاسبية واقتراح قيد يومية، يجب أولاً قراءة شجرة الحسابات الحالية من النظام باستخدام أدوات MCP قبل اقتراح أي حساب.
- ممنوع اقتراح أي حساب بالاعتماد على المعرفة العامة إذا لم يكن الحساب موجوداً فعلياً في شجرة الحسابات الحالية.
- كل حساب في أي قيد مقترح يجب أن يكون موجوداً فعلياً في النظام، ويجب ذكر اسم الحساب ورقمه كما هو مسجل.
- إذا لم يوجد الحساب المناسب، لا تخترع حساباً ولا تعتبر حساباً قريباً بديلاً صحيحاً تلقائياً؛ اذكر الحسابات الموجودة ذات الصلة بوضوح، واطلب من المستخدم اختيار حساب موجود أو طلب إنشاء حساب جديد.
- بالنسبة لضريبة القيمة المضافة، يجب التحقق من حساب VAT الفعلي الموجود في شجرة الحسابات قبل اقتراح أي قيد ضريبي، وعدم افتراض اسم أو نوع الحساب.
- لا تقترح القيد المحاسبي النهائي إلا بعد إتمام مطابقة الحسابات مع شجرة الحسابات الحالية.
- لا ترسل أي فاتورة أو مستند تلقائيًا لمجرد أن المستخدم قال إن الإجابة صحيحة أو شكر المساعد.
- لا تخترع أسماء أو أرقام مستندات أو مبالغ أو تواريخ أو حسابات.

قواعد سلف الموظفين ومصروفاتهم:
- استخدم Employee Advance لإدارة سلفة الموظف، وExpense Claim لتسجيل المصروفات الفعلية.
- استخدم أدوات MCP المتخصصة عندما تكون متاحة، ولا تستخدم erpnext_doc_create لإنشاء Expense Claim.
- عند طلب إنشاء سلفة، ابحث أولاً عن الموظف والشركة والعملة والحساب/طريقة الدفع المناسبة من النظام، ثم أنشئ Employee Advance بالحقول الفعلية المطلوبة.
- عند تسجيل مصروف من سلفة: استخدم حصراً أداة erpnext_expense_claim_create إذا كانت متاحة، ولا تستخدم erpnext_doc_create لإنشاء Expense Claim. يجب أن يكون Expense Claim مرتبطاً فعلياً بالسلفة من خلال advances/Expense Claim Advance.
- قاعدة إلزامية لسلف الموظفين: حالة Employee Advance = "Paid" تعني فقط أن مبلغ السلفة تم دفعه للموظف، ولا تعني أن السلفة استُهلكت أو أُغلقت.
- ممنوع منعًا باتًا استخدام status أو pending_amount للحكم على المبلغ المتاح للمطالبة من السلفة.
- عند سؤال المستخدم عن المتاح من السلفة، يجب قراءة المستند الحالي من النظام والحصول صراحةً على الحقول: advance_amount وclaimed_amount وreturn_amount.
- احسب المبلغ المتاح للمطالبة بهذه المعادلة فقط: available_amount = advance_amount - claimed_amount - return_amount.
- pending_amount ليس المبلغ المتاح للمطالبة؛ لا تستخدمه في هذه المعادلة ولا تستنتج منه أن الرصيد المتاح صفر.
- مثال إلزامي: إذا كانت advance_amount=1000 وclaimed_amount=0 وreturn_amount=0 وstatus=Paid وpending_amount=0، فالنتيجة الصحيحة هي available_amount=1000 ريال، وليس صفر.
- إذا لم تظهر advance_amount أو claimed_amount أو return_amount في نتيجة القراءة، نفّذ قراءة أخرى للمستند نفسه بالحقول المطلوبة ولا تخمّن الرصيد.
- لا تقل إن السلفة منتهية أو لا يوجد بها رصيد إلا إذا كان available_amount المحسوب بهذه المعادلة يساوي صفرًا أو أقل.
- عند تسجيل مصروف من سلفة، يجب أن يحتوي Expense Claim على رابط فعلي إلى Employee Advance من خلال جدول Expense Claim Advance، مع تخصيص مبلغ المصروف للسلفة، وليس مجرد ذكر رقم السلفة في الوصف أو النص.
- بعد إنشاء Expense Claim المرتبط بالسلفة، أعد قراءة Expense Claim وEmployee Advance للتحقق من الربط والمبالغ، وتأكد أن claimed_amount في السلفة انعكس وفقًا للعملية التي نفذها النظام.
- كل بند مصروف يجب أن يحتفظ بنوع المصروف ووصفه ومبلغه، ولا تدمج أنواع المصروفات المختلفة في بند واحد.
- Expense Claim Type يحتوي على أنواع المصروفات، والحساب الافتراضي للشركة موجود في جدول Expense Claim Account المرتبط به. ابحث عن الـmapping الفعلي قبل إنشاء المصروف.
- لا تستخدم أسماء أو أرقام حسابات ثابتة داخل إجاباتك أو عمليات الإنشاء. الحسابات يجب أن تأتي من بيانات الشركة الحالية.
- لا تنشئ حساب GL لكل موظف. استخدم حساب السلف العام المهيأ في النظام مع تتبع الموظف من خلال Employee Advance وExpense Claim.
- إذا لم يوجد Expense Claim Type مناسب أو لا يوجد default_account صالح للشركة، لا تخمن ولا تختار حساباً قريباً؛ أوقف الإنشاء واطلب تحديد الإعداد الصحيح.
- عند سؤال المستخدم عن رصيد سلفة أو إجمالي مصروفات موظف أو إجمالي نوع مصروف، نفذ قراءة جديدة من النظام ولا تنشئ أي مستند.
- مثال: إذا قال المستخدم "علي صرف 200 بنزين و50 مسامير من عهدته"، افهمها كمصروفين منفصلين مرتبطين بسلفة علي، وابحث عن النوع والحساب لكل بند قبل الإنشاء.
- قبل أي إنشاء أو تعديل، تحقق من أن الموظف والسلفة والمبالغ والبنود المقصودة هي الموجودة فعلياً في النظام.
- بعد أي إنشاء أو تعديل، اقرأ المستند الناتج من النظام وتحقق من الموظف والمبلغ والبنود والسلفة المرتبطة والحالة، ولا تقل إن العملية نجحت إلا بعد نجاح قراءة التحقق.
"""


@frappe.whitelist(allow_guest=False)
def ask_gemini(question, conversation_id=None, mobile=None, pdf_base64=None, filename=None):
    gemini_api_key = frappe.conf.get("gemini_api_key")
    mcp_token = frappe.conf.get("mcp_token")
    mcp_url = frappe.conf.get("mcp_url", "http://mcp-erpnext:3012/mcp")

    # Gemini أولاً لأننا نحتاج دعم function calling بشكل موثوق.
    models = ["gemini-3.1-flash-lite", "gemini-3.5-flash-lite", "gemma-4-26b-a4b-it"]

    if not gemini_api_key or not mcp_token:
        frappe.throw("خطأ: مفاتيح الإعدادات غير موجودة.")

    if not question:
        frappe.throw("خطأ: يرجى إرسال سؤال.")

    def mcp_call(method, params=None, req_id=1):
        params = dict(params or {})
        meta = dict(params.get("_meta") or {})
        meta.setdefault(
            "io.modelcontextprotocol/protocolVersion",
            "2026-07-28",
        )
        meta.setdefault(
            "io.modelcontextprotocol/clientInfo",
            {"name": "frappe-gateway", "version": "1.0"},
        )
        meta.setdefault(
            "io.modelcontextprotocol/clientCapabilities",
            {},
        )
        params["_meta"] = meta

        payload = json.dumps({
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
            "params": params,
        }).encode("utf-8")

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "Authorization": f"Bearer {mcp_token}",
            "MCP-Protocol-Version": "2026-07-28",
            "Mcp-Method": method,
        }

        if method == "tools/call":
            tool_name = str(params.get("name") or "")
            if tool_name:
                headers["Mcp-Name"] = tool_name

        req = urllib.request.Request(
            mcp_url,
            data=payload,
            headers=headers,
        )

        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            frappe.throw(
                f"فشل الاتصال بسيرفر MCP: HTTP {e.code}: {body[:500]}"
            )
        except urllib.error.URLError as e:
            frappe.throw(f"فشل الاتصال بسيرفر MCP: {str(e)}")

    def gemini_call(payload):
        for attempt in range(len(models) * 2):
            current_model = models[attempt % len(models)]

            url = (
                "https://generativelanguage.googleapis.com/v1beta/models/"
                + current_model
                + ":generateContent?key="
                + gemini_api_key
            )

            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
            )

            try:
                with urllib.request.urlopen(req, timeout=60) as resp:
                    return json.loads(resp.read().decode("utf-8"))

            except urllib.error.HTTPError as e:
                body = e.read().decode("utf-8", errors="replace")
                if e.code in (429, 503, 404):
                    time.sleep(2)
                    continue
                frappe.throw(f"خطأ Gemini ({e.code}): {body[:1500]}")

            except urllib.error.URLError:
                frappe.throw("فشل الاتصال بخدمة Gemini")

        frappe.throw("تجاوز عدد المحاولات.")

    # MCP tools
    mcp_call(
        "initialize",
        {
            "protocolVersion": "2026-07-28",
            "capabilities": {},
            "clientInfo": {
                "name": "frappe-gateway",
                "version": "1.0",
            },
            "_meta": {
                "io.modelcontextprotocol/protocolVersion": "2026-07-28"
            },
        },
        req_id=1,
    )

    tools_resp = mcp_call("tools/list", req_id=2)
    mcp_tools = tools_resp.get("result", {}).get("tools", [])

    def normalize_gemini_schema(schema):
        """
        Convert MCP JSON Schema to the subset accepted by Gemini
        Function Calling, without changing the original schema used
        when executing the MCP tool.
        """
        if not isinstance(schema, dict):
            return {"type": "object", "properties": {}}

        # Resolve union schemas conservatively.
        if "anyOf" in schema and isinstance(schema["anyOf"], list):
            choices = [
                x for x in schema["anyOf"]
                if isinstance(x, dict)
                and x.get("type") != "null"
            ]
            if choices:
                merged = dict(choices[0])
                if len(choices) > 1 and "description" not in merged:
                    merged["description"] = schema.get("description", "")
                schema = merged
            else:
                schema = {"type": "string"}

        if "oneOf" in schema and isinstance(schema["oneOf"], list):
            choices = [
                x for x in schema["oneOf"]
                if isinstance(x, dict)
                and x.get("type") != "null"
            ]
            schema = dict(choices[0]) if choices else {"type": "string"}

        out = {}

        # Gemini Function Calling schema supports a restricted set.
        allowed = {
            "title",
            "description",
            "type",
            "format",
            "enum",
            "properties",
            "required",
            "items",
            "minimum",
            "maximum",
            "minItems",
            "maxItems",
            "nullable",
        }

        for key in allowed:
            if key in schema:
                out[key] = schema[key]

        # JSON Schema may use a union such as ["string", "array"].
        # Gemini Function Calling requires exactly one concrete type.
        schema_type = schema.get("type")
        if isinstance(schema_type, list):
            non_null = [x for x in schema_type if x != "null"]
            if non_null:
                if "array" in non_null and isinstance(schema.get("items"), dict):
                    out["type"] = "array"
                elif "object" in non_null and isinstance(schema.get("properties"), dict):
                    out["type"] = "object"
                else:
                    out["type"] = non_null[0]
                if "null" in schema_type:
                    out["nullable"] = True
            else:
                out["type"] = "string"

        # Some MCP schemas use tuple-style prefixItems.
        # Gemini function calling wants a single items schema.
        if "prefixItems" in schema and "items" not in schema:
            prefix = schema.get("prefixItems")
            if isinstance(prefix, list) and prefix:
                out["items"] = normalize_gemini_schema(prefix[0])

        if isinstance(schema.get("properties"), dict):
            out["properties"] = {
                str(name): normalize_gemini_schema(value)
                for name, value in schema["properties"].items()
                if isinstance(value, dict)
            }

        if isinstance(schema.get("items"), dict):
            out["items"] = normalize_gemini_schema(schema["items"])

        if isinstance(out.get("required"), list):
            out["required"] = [
                str(x) for x in out["required"]
                if isinstance(x, str)
            ]

        # Gemini does not need OpenAPI/JSON-Schema additionalProperties
        # for function calling. Drop it rather than sending an invalid field.

        if "type" not in out:
            if "properties" in out:
                out["type"] = "object"
            elif "items" in out:
                out["type"] = "array"
            else:
                out["type"] = "object"

        return out

    # Gemini يرى كل أدوات MCP ويمكنه استدعاء أي أداة عند طلب المستخدم.
    safe_mcp_tools = list(mcp_tools)

    gemini_declarations = [
        {
            "name": t["name"],
            "description": t.get("description", ""),
            "parameters": normalize_gemini_schema(
                t.get(
                    "inputSchema",
                    {"type": "object", "properties": {}},
                )
            ),
        }
        for t in safe_mcp_tools
    ]

    # أدوات PDF محلية. الأداة العامة تحافظ على نوع المستند.
    gemini_declarations.append(
        {
            "name": "send_document_pdf",
            "description": (
                "إرسال PDF لأي مستند موجود بالفعل إلى نفس رقم واتساب. "
                "استخدمها لـ Quotation أو Sales Invoice أو Sales Order أو غيرها. "
                "يجب تمرير doctype وdocument_name الصحيحين. لا تحول عرض السعر إلى فاتورة."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "doctype": {
                        "type": "string",
                        "description": "نوع المستند الفعلي مثل Quotation أو Sales Invoice"
                    },
                    "document_name": {
                        "type": "string",
                        "description": "اسم المستند الفعلي في النظام"
                    },
                },
                "required": ["doctype", "document_name"],
            },
        }
    )

    gemini_declarations.append(
        {
            "name": "send_invoice_pdf",
            "description": (
                "إرسال PDF لـ Sales Invoice فقط. ممنوع استخدامها لعروض الأسعار "
                "أو أوامر البيع أو أي مستند آخر."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "invoice_name": {
                        "type": "string",
                        "description": "اسم Sales Invoice الفعلي"
                    }
                },
                "required": ["invoice_name"],
            },
        }
    )

    gemini_tools = [
        {
            "functionDeclarations": gemini_declarations
        }
    ]

    # ذاكرة المحادثة
    memory_key = (
        f"hagag_ai_wa_memory:{conversation_id}"
        if conversation_id
        else None
    )

    history = []

    if memory_key:
        try:
            history = frappe.cache().get_value(memory_key) or []
        except Exception:
            history = []

    recent = history[-10:]

    messages = []

    for item in recent:
        role = item.get("role")
        text = item.get("text")

        if role in ("user", "model") and text:
            messages.append(
                {
                    "role": role,
                    "parts": [{"text": text}],
                }
            )

    # لو المستخدم قال "أيوة" بعد سؤال تأكيد، نخلي السياق صريح جداً.
    q_lower = (question or "").strip().lower()

    # آخر مستند معروف في سياق المحادثة.
    last_document = None
    document_patterns = [
        (r"SAL-QTN-[A-Za-z0-9-]+", "Quotation"),
        (r"ACC-SINV-[A-Za-z0-9-]+", "Sales Invoice"),
        (r"SAL-ORD-[A-Za-z0-9-]+", "Sales Order"),
        (r"ACC-PINV-[A-Za-z0-9-]+", "Purchase Invoice"),
        (r"PUR-ORD-[A-Za-z0-9-]+", "Purchase Order"),
        (r"ACC-JV-[A-Za-z0-9-]+", "Journal Entry"),
    ]

    for item in reversed(history):
        htext = str(item.get("text", ""))
        for pattern, doctype in document_patterns:
            match = re.search(pattern, htext)
            if match:
                last_document = {
                    "doctype": doctype,
                    "name": match.group(0),
                }
                break
        if last_document:
            break

    # المستند الموجود في السؤال الحالي له الأولوية.
    for pattern, doctype in document_patterns:
        match = re.search(pattern, question or "")
        if match:
            last_document = {
                "doctype": doctype,
                "name": match.group(0),
            }
            break

    last_invoice = None

    if conversation_id:
        try:
            last_invoice = frappe.cache().get_value(
                f"hagag_ai_last_invoice:{conversation_id}"
            )
        except Exception:
            last_invoice = None

    # WhatsApp قد يستخدم JID مختلف لنفس المستخدم، لذلك استخدم رقم الهاتف كنسخة احتياطية.
    if not last_invoice and mobile:
        try:
            cache_mobile = re.sub(r"\D", "", str(mobile))
            if cache_mobile:
                last_invoice = frappe.cache().get_value(
                    f"hagag_ai_last_invoice_mobile:{cache_mobile}"
                )
        except Exception:
            last_invoice = None

    question_invoice = re.search(r"ACC-SINV-[A-Za-z0-9-]+", question or "")
    if question_invoice:
        candidate_invoice = question_invoice.group(0)
        if frappe.db.exists("Sales Invoice", candidate_invoice):
            last_invoice = candidate_invoice

    if not last_invoice:
        for item in reversed(history):
            text = item.get("text", "")
            match = re.search(
                r"ACC-SINV-[A-Za-z0-9-]+",
                text,
            )
            if match and frappe.db.exists("Sales Invoice", match.group(0)):
                last_invoice = match.group(0)
                break

    approval_words = [
        "ايوة",
        "أيوة",
        "ايوه",
        "أيوه",
        "نعم",
        "اه",
        "آه",
        "تمام",
        "موافق",
    ]

    pdf_words = [
        "pdf",
        "بي دي اف",
        "بي ديإف",
        "ابعته",
        "ابعتها",
        "ابعت",
        "أرسلها",
        "ارسله",
    ]

    invoice_only_request = bool(
        question_invoice
        and re.fullmatch(r"\s*ACC-SINV-[A-Za-z0-9-]+\s*", question or "")
    )

    pdf_request = (
        any(x in q_lower for x in pdf_words)
        or (
            invoice_only_request
            and last_invoice
        )
    )

    if pdf_request and last_document:
        messages.append(
            {
                "role": "user",
                "parts": [
                    {
                        "text": (
                            "المستند المؤكد في السياق هو "
                            + last_document["doctype"]
                            + " باسم "
                            + last_document["name"]
                            + ". المستخدم يطلب إرسال هذا المستند PDF. "
                            "استخدم send_document_pdf بنفس النوع والاسم. "
                            "ممنوع استبداله بفاتورة أو بأي مستند آخر."
                        )
                    }
                ],
            }
        )
    elif pdf_request and last_invoice:
        messages.append(
            {
                "role": "user",
                "parts": [
                    {
                        "text": (
                            "الفاتورة المؤكدة هي "
                            + last_invoice
                            + ". استخدم send_document_pdf مع "
                            "doctype=Sales Invoice وdocument_name="
                            + last_invoice
                            + "."
                        )
                    }
                ],
            }
        )
    else:
        current_parts = [{"text": question}]
        if pdf_base64:
            current_parts.append(
                {
                    "inline_data": {
                        "mime_type": "application/pdf",
                        "data": str(pdf_base64),
                    }
                }
            )
        messages.append(
            {
                "role": "user",
                "parts": current_parts,
            }
        )

    max_steps = 8
    verification_pending = False
    verification_requested = False

    for step in range(max_steps):
        payload = {
            "systemInstruction": {
                "parts": [{"text": SYSTEM_INSTRUCTION}]
            },
            "contents": messages,
            "tools": gemini_tools,
        }

        # عند طلب PDF نمنع Gemini من الرد بالكلام فقط.
        if pdf_request and last_invoice:
            payload["toolConfig"] = {
                "functionCallingConfig": {
                    "mode": "ANY",
                    "allowedFunctionNames": ["send_invoice_pdf"],
                }
            }

        resp = gemini_call(payload)

        if "candidates" not in resp or not resp["candidates"]:
            frappe.throw("رد غير متوقع من Gemini.")

        model_parts = (
            resp["candidates"][0]
            .get("content", {})
            .get("parts", [])
        )

        messages.append(
            {
                "role": "model",
                "parts": model_parts,
            }
        )

        fc_part = next(
            (
                p
                for p in model_parts
                if "functionCall" in p
            ),
            None,
        )

        if fc_part:
            fc = fc_part["functionCall"]
            function_name = fc.get("name", "")
            args = fc.get("args", {}) or {}

            # إرسال PDF لأي نوع مستند مع الحفاظ على النوع والاسم.
            if function_name == "erpnext_doc_create":
                create_doctype = str(args.get("doctype") or "").strip()
                if create_doctype == "Expense Claim":
                    tool_result = {
                        "status": "error",
                        "operation": function_name,
                        "message": (
                            "Expense Claim يجب إنشاؤه حصراً باستخدام "
                            "erpnext_expense_claim_create. "
                            "أعد المحاولة باستخدام الأداة المتخصصة."
                        ),
                    }
                    write_failed = True
                    messages.append(
                        {
                            "role": "user",
                            "parts": [
                                {
                                    "functionResponse": {
                                        "name": function_name,
                                        "response": {
                                            "result": tool_result
                                        },
                                    }
                                }
                            ],
                        }
                    )
                    pdf_request = False
                    continue

            if function_name in ("send_document_pdf", "send_invoice_pdf"):
                if function_name == "send_invoice_pdf":
                    doctype = "Sales Invoice"
                    document_name = str(
                        args.get("invoice_name", "")
                    ).strip()
                else:
                    doctype = str(
                        args.get("doctype", "")
                    ).strip()
                    document_name = str(
                        args.get("document_name", "")
                    ).strip()

                if (
                    not conversation_id
                    or not mobile
                    or not doctype
                    or not document_name
                ):
                    tool_result = {
                        "status": "error",
                        "message": "بيانات المستند أو المحادثة غير مكتملة.",
                    }
                elif not frappe.db.exists(doctype, document_name):
                    tool_result = {
                        "status": "error",
                        "message": "المستند المطلوب غير موجود.",
                    }
                else:
                    try:
                        mobile_clean = (
                            str(mobile)
                            .strip()
                            .replace(" ", "")
                            .replace("-", "")
                        )

                        if mobile_clean.startswith("00"):
                            mobile_clean = mobile_clean[2:]
                        elif mobile_clean.startswith("0") and len(mobile_clean) == 10:
                            mobile_clean = "966" + mobile_clean[1:]

                        pdf = frappe.get_print(
                            doctype,
                            document_name,
                            as_pdf=True,
                        )

                        payload = json.dumps(
                            {
                                "number": mobile_clean,
                                "message": (
                                    f"مستند {document_name} "
                                    "من حجاج للمقاولات"
                                ),
                                "pdf_base64": base64.b64encode(
                                    pdf
                                ).decode("ascii"),
                                "filename": document_name + ".pdf",
                            }
                        ).encode("utf-8")

                        req = urllib.request.Request(
                            "http://wa-baileys:3000/send",
                            data=payload,
                            headers={
                                "Content-Type": "application/json",
                                "Authorization": (
                                    "Bearer HAGAG_WA_7f3c9a2d6e4b8a1c"
                                ),
                            },
                            method="POST",
                        )

                        with urllib.request.urlopen(
                            req,
                            timeout=30,
                        ) as resp:
                            tool_result = json.loads(
                                resp.read().decode("utf-8")
                            )

                    except Exception:
                        frappe.log_error(
                            frappe.get_traceback(),
                            "Hagag AI PDF Send Error",
                        )
                        tool_result = {
                            "status": "error",
                            "message": "فشل إرسال ملف المستند PDF.",
                        }

            # جميع أدوات MCP متاحة للتنفيذ.
            else:
                mcp_res = mcp_call(
                    "tools/call",
                    {"name": function_name, "arguments": args},
                    req_id=10 + step,
                )

                # نتيجة MCP هي المصدر الوحيد للحكم على نجاح العملية.
                # لا نعتبر الكتابة ناجحة إذا أعاد MCP خطأ.
                mcp_result = mcp_res.get("result", mcp_res)
                mcp_error = mcp_res.get("error")

                if isinstance(mcp_result, dict):
                    if mcp_result.get("isError") is True:
                        mcp_error = mcp_result
                    elif mcp_result.get("error"):
                        mcp_error = mcp_result.get("error")

                if mcp_error:
                    tool_result = {
                        "status": "error",
                        "operation": function_name,
                        "message": "فشلت العملية في النظام. لا تعتبر العملية ناجحة.",
                        "details": mcp_error,
                    }
                    write_failed = True
                else:
                    tool_result = mcp_result
                    write_failed = False

                # بعد الكتابة الناجحة فقط نطلب تحققًا جديدًا من النظام.
                fn_lower = function_name.lower()

                write_markers = (
                    "create",
                    "update",
                    "delete",
                    "submit",
                    "cancel",
                    "assign",
                    "approve",
                    "reject",
                    "insert",
                    "set",
                    "rename",
                    "duplicate",
                    "restore",
                    "close",
                    "move",
                    "add",
                    "remove",
                )

                read_markers = (
                    "get",
                    "list",
                    "search",
                    "fetch",
                    "read",
                    "count",
                    "report",
                    "detail",
                )

                if any(x in fn_lower for x in write_markers):
                    if write_failed:
                        verification_pending = False
                        verification_requested = False
                    else:
                        verification_pending = True
                        verification_requested = False

                elif (
                    any(x in fn_lower for x in read_markers)
                    and verification_pending
                ):
                    verification_pending = False
                    verification_requested = False

            messages.append(
                {
                    "role": "user",
                    "parts": [
                        {
                            "functionResponse": {
                                "name": function_name,
                                "response": {
                                    "result": tool_result
                                },
                            }
                        }
                    ],
                }
            )

            # بعد الكتابة، نطلب من Gemini قراءة تحقق جديدة قبل الرد النهائي.
            if verification_pending and not verification_requested:
                messages.append(
                    {
                        "role": "user",
                        "parts": [
                            {
                                "text": (
                                    "هذه نتيجة عملية كتابة. لا تُنهِ الرد بعد. "
                                    "نفّذ الآن قراءة تحقق جديدة من النظام للتأكد "
                                    "من وجود المستند/القيد وحالته. وفي العمليات "
                                    "المحاسبية تحقق من الحسابات والمبالغ وتوازن "
                                    "المدين والدائن."
                                )
                            }
                        ],
                    }
                )
                verification_requested = True

            pdf_request = False
            continue

        if verification_pending:
            if not verification_requested:
                messages.append(
                    {
                        "role": "user",
                        "parts": [
                            {
                                "text": (
                                    "لا تُنهِ الرد. يجب تنفيذ قراءة تحقق جديدة "
                                    "من النظام الآن بعد عملية الكتابة."
                                )
                            }
                        ],
                    }
                )
                verification_requested = True
                continue

            return {
                "status": "warning",
                "message": (
                    "تم تنفيذ العملية، لكن لم تكتمل قراءة التحقق النهائية. "
                    "راجع المستند من النظام قبل الاعتماد."
                ),
            }

        text = next(
            (
                p.get("text", "")
                for p in model_parts
                if "text" in p and not p.get("thought")
            ),
            "تمت العملية.",
        )

        # حفظ الذاكرة
        if conversation_id:
            try:
                history.append(
                    {
                        "role": "user",
                        "text": question,
                    }
                )
                history.append(
                    {
                        "role": "model",
                        "text": text,
                    }
                )

                frappe.cache().set_value(
                    memory_key,
                    history[-15:],
                    expires_in_sec=86400,
                )
            except Exception:
                pass

        # حفظ آخر مستند معروف في الذاكرة.
        invoice_match = re.search(
            r"ACC-SINV-[A-Za-z0-9-]+",
            text,
        )

        document_match = None

        for pattern, doctype in document_patterns:
            match = re.search(pattern, text)
            if match:
                document_match = {
                    "doctype": doctype,
                    "name": match.group(0),
                }
                break

        if conversation_id and invoice_match:
            try:
                invoice_name = invoice_match.group(0)

                if frappe.db.exists("Sales Invoice", invoice_name):
                    frappe.cache().set_value(
                        f"hagag_ai_last_invoice:{conversation_id}",
                        invoice_name,
                        expires_in_sec=86400,
                    )

                    if mobile:
                        cache_mobile = re.sub(r"\D", "", str(mobile))
                        if cache_mobile:
                            frappe.cache().set_value(
                                f"hagag_ai_last_invoice_mobile:{cache_mobile}",
                                invoice_name,
                                expires_in_sec=86400,
                            )

                    # ضم رقم الفاتورة للذاكرة نفسها، كنسخة احتياطية.
                    history.append({
                        "role": "context",
                        "text": f"الفاتورة الحالية في المحادثة: {invoice_name}",
                    })
                    frappe.cache().set_value(
                        memory_key,
                        history[-15:],
                        expires_in_sec=86400,
                    )
            except Exception:
                pass

        if conversation_id and document_match:
            try:
                frappe.cache().set_value(
                    f"hagag_ai_last_document:{conversation_id}",
                    document_match,
                    expires_in_sec=86400,
                )
            except Exception:
                pass

        return {
            "status": "success",
            "message": text,
        }

    return {
        "status": "warning",
        "message": "استغرق وقتاً طويلاً. حاول تبسيط السؤال.",
    }
