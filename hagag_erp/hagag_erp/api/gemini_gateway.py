import frappe
import json
import urllib.request
import urllib.error
import time


@frappe.whitelist(allow_guest=False)
def ask_gemini(question):
    gemini_api_key = frappe.conf.get("gemini_api_key")
    mcp_token = frappe.conf.get("mcp_token")
    mcp_url = frappe.conf.get("mcp_url", "http://mcp-erpnext:3012/mcp")
    gemini_model = "gemini-3.1-flash-lite"

    if not gemini_api_key or not mcp_token:
        frappe.throw("خطأ: لم يتم العثور على مفاتيح Gemini أو MCP في الإعدادات.")
    if not question:
        frappe.throw("خطأ: يرجى إرسال سؤال (question).")

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
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{gemini_model}:generateContent?key={gemini_api_key}"
        req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"})
        for attempt in range(4):
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as e:
                body = e.read().decode("utf-8", errors="ignore")
                if e.code in (429, 503):
                    time.sleep(15)
                    continue
                if e.code == 404:
                    frappe.throw(f"الموديل {gemini_model} غير متاح حاليًا. تفاصيل: {body}")
                frappe.throw(f"خطأ من Gemini ({e.code}): {body}")
            except urllib.error.URLError as e:
                frappe.throw(f"فشل الاتصال بخدمة Gemini: {str(e)}")
        frappe.throw("تم تجاوز عدد محاولات الاتصال بـ Gemini بسبب ضغط أو حد الاستخدام.")

    mcp_call("initialize", {
        "protocolVersion": "2026-07-28", "capabilities": {},
        "clientInfo": {"name": "frappe-gateway", "version": "1.0"},
        "_meta": {"io.modelcontextprotocol/protocolVersion": "2026-07-28"}
    }, req_id=1)

    tools_resp = mcp_call("tools/list", req_id=2)
    mcp_tools = tools_resp.get("result", {}).get("tools", [])
    if not mcp_tools:
        frappe.throw("لم يتم العثور على أدوات (Tools) في سيرفر MCP.")

    gemini_tools = [{"functionDeclarations": [
        {"name": t["name"], "description": t.get("description", ""), "parameters": t.get("inputSchema", {"type": "object", "properties": {}})}
        for t in mcp_tools
    ]}]

    messages = [{"role": "user", "parts": [{"text": question}]}]
    max_steps = 5

    for step in range(max_steps):
        resp = gemini_call({"contents": messages, "tools": gemini_tools})
        if "candidates" not in resp or not resp["candidates"]:
            frappe.throw("رد غير متوقع من Gemini.")
        part = resp["candidates"][0]["content"]["parts"][0]

        if "functionCall" in part:
            fc = part["functionCall"]
            mcp_res = mcp_call("tools/call", {"name": fc["name"], "arguments": fc.get("args", {})}, req_id=10 + step)
            tool_result = mcp_res.get("result", mcp_res)
            messages.append({"role": "model", "parts": [part]})
            messages.append({"role": "user", "parts": [{"functionResponse": {"name": fc["name"], "response": {"result": tool_result}}}]})
        else:
            return {"status": "success", "message": part.get("text", "تمت العملية بدون رد نصي.")}

    return {"status": "warning", "message": "استغرق الذكاء الاصطناعي خطوات كثيرة جدًا. حاول تصيغ السؤال بشكل أبسط."}
