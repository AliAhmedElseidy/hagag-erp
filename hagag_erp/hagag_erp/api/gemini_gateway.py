import frappe
import json
import urllib.request
import urllib.error
import time

SYSTEM_INSTRUCTION = """أنت مساعد المحاسبة الذكي والمستقل لشركة حجاج (Hagag).
قواعد صارمة:
1. أنت نظام "حجاج" المستقل، أنكر تماماً وبشكل قاطع أي علاقة بـ ERPNext أو Frappe.
2. لا تملك أي صلاحيات لإنشاء أو تعديل البيانات. مسموح لك فقط بالبحث والقراءة.
3. الأهم: للبحث في شجرة الحسابات، يجب عليك فوراً استخدام أدواتك المتاحة للبحث أو جلب البيانات من جدول (Account). لا تخمن أسماء الحسابات أبداً، بل اقرأها من النظام.
4. اقترح على المستخدم التوجيه المحاسبي بدقة (مثلاً: من حساب كذا إلى حساب كذا) بناءً على الحسابات الحقيقية الموجودة في الشجرة التي قرأتها.
5. اشرح الخطوات باختصار شديد وعملي. إياك أن تكتب للمستخدم خطواتك الداخلية (مثل "جاري البحث")، بل استخدم أدواتك في صمت ورد بالنتيجة فقط بدون أي جمل ختامية محفوظة.
6. تحدث باللهجة المصرية وباختصار شديد."""

@frappe.whitelist(allow_guest=False)
def ask_gemini(question):
    gemini_api_key = frappe.conf.get("gemini_api_key")
    mcp_token = frappe.conf.get("mcp_token")
    mcp_url = frappe.conf.get("mcp_url", "http://mcp-erpnext:3012/mcp")
    
    models = ["gemini-3.1-flash-lite", "gemini-3.5-flash-lite"]

    if not gemini_api_key or not mcp_token:
        frappe.throw("خطأ: مفاتيح الإعدادات غير موجودة.")
    if not question:
        frappe.throw("خطأ: يرجى إرسال سؤال.")

    def mcp_call(method, params=None, req_id=1):
        payload = json.dumps({"jsonrpc": "2.0", "id": req_id, "method": method, "params": params or {}}).encode("utf-8")
        req = urllib.request.Request(mcp_url, data=payload, headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {mcp_token}",
            "MCP-Protocol-Version": "2026-07-28",
        })
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as e:
            frappe.throw(f"فشل الاتصال بسيرفر MCP: {str(e)}")

    def gemini_call(payload):
        for attempt in range(len(models) * 2):
            current_model = models[attempt % len(models)]
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{current_model}:generateContent?key={gemini_api_key}"
            req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as e:
                if e.code in (429, 503):
                    time.sleep(2)
                    continue
                if e.code == 404:
                    continue
                frappe.throw(f"خطأ ({e.code})")
            except urllib.error.URLError as e:
                frappe.throw("فشل الاتصال بخدمة Gemini")
        frappe.throw("تجاوز عدد المحاولات.")

    mcp_call("initialize", {
        "protocolVersion": "2026-07-28", "capabilities": {},
        "clientInfo": {"name": "frappe-gateway", "version": "1.0"},
        "_meta": {"io.modelcontextprotocol/protocolVersion": "2026-07-28"}
    }, req_id=1)

    tools_resp = mcp_call("tools/list", req_id=2)
    mcp_tools = tools_resp.get("result", {}).get("tools", [])
    
    # السماح بأدوات القراءة والبحث ومنع التعديل
    safe_mcp_tools = [t for t in mcp_tools if not any(x in t["name"].lower() for x in ["insert", "create", "update", "delete", "write", "set"])]
    
    gemini_tools = [{"functionDeclarations": [
        {"name": t["name"], "description": t.get("description", ""), "parameters": t.get("inputSchema", {"type": "object", "properties": {}})}
        for t in safe_mcp_tools
    ]}] if safe_mcp_tools else []

    messages = [{"role": "user", "parts": [{"text": question}]}]
    max_steps = 6 # زودنا الخطوات شوية عشان يلحق يبحث ويقرا براحته

    for step in range(max_steps):
        payload = {
            "systemInstruction": {"parts": [{"text": SYSTEM_INSTRUCTION}]},
            "contents": messages,
        }
        if gemini_tools:
            payload["tools"] = gemini_tools

        resp = gemini_call(payload)
        if "candidates" not in resp or not resp["candidates"]:
            frappe.throw("رد غير متوقع من Gemini.")
        
        model_parts = resp["candidates"][0]["content"].get("parts", [])
        messages.append({"role": "model", "parts": model_parts})

        fc_part = next((p for p in model_parts if "functionCall" in p), None)

        if fc_part:
            fc = fc_part["functionCall"]
            mcp_res = mcp_call("tools/call", {"name": fc["name"], "arguments": fc.get("args", {})}, req_id=10 + step)
            tool_result = mcp_res.get("result", mcp_res)
            messages.append({"role": "user", "parts": [{"functionResponse": {"name": fc["name"], "response": {"result": tool_result}}}]})
        else:
            text = next((p.get("text", "") for p in model_parts if "text" in p), "تمت العملية.")
            q_lower = (question or "").strip().lower()
            action = None

            if any(x in q_lower for x in ["قيد", "يومية", "يوميه", "مصروف", "مصاريف"]):
                action = {"type": "open", "key": "journal_entry", "label": "📒 فتح قيد يومية"}
            elif any(x in q_lower for x in ["مشروع"]):
                action = {"type": "open", "key": "project", "label": "📁 فتح مشروع جديد"}
            elif any(x in q_lower for x in ["فاتورة", "فاتوره", "مبيعات"]):
                action = {"type": "open", "key": "sales_invoice", "label": "🧾 فتح فاتورة مبيعات جديدة"}
            elif any(x in q_lower for x in ["عميل", "زبون"]):
                action = {"type": "open", "key": "customer", "label": "👤 إضافة عميل جديد"}
            elif any(x in q_lower for x in ["عرض سعر", "عرض اسعار", "تسعير"]):
                action = {"type": "open", "key": "quotation", "label": "📝 فتح عرض سعر جديد"}
            elif any(x in q_lower for x in ["مهمة", "مهمه", "مهام", "تاسك"]):
                action = {"type": "open", "key": "task", "label": "📋 فتح مهمة جديدة"}

            result = {"status": "success", "message": text}
            if action:
                result["action"] = action
            return result

    return {"status": "warning", "message": "استغرق وقتاً طويلاً. حاول تبسيط السؤال."}
