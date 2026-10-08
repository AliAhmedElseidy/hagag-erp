(() => {
  "use strict";

  function injectStyles() {
    const css = `
      #hagag-chat-btn{position:fixed;bottom:24px;left:24px;width:56px;height:56px;border-radius:50%;
        background:#d97706;color:#fff;display:flex;align-items:center;justify-content:center;
        box-shadow:0 4px 12px rgba(0,0,0,.25);cursor:pointer;z-index:9999;font-size:26px;border:none;}
      #hagag-chat-panel{position:fixed;bottom:92px;left:24px;width:340px;max-width:90vw;height:460px;
        max-height:70vh;background:var(--card-bg,#fff);border-radius:12px;box-shadow:0 8px 24px rgba(0,0,0,.3);
        display:none;flex-direction:column;z-index:9999;overflow:hidden;border:1px solid rgba(0,0,0,.08);}
      #hagag-chat-panel.open{display:flex;}
      #hagag-chat-header{background:#d97706;color:#fff;padding:10px 14px;font-weight:600;display:flex;justify-content:space-between;align-items:center;}
      #hagag-chat-header span.close{cursor:pointer;font-size:18px;}
      #hagag-chat-log{flex:1;overflow-y:auto;padding:10px;font-size:13px;direction:rtl;text-align:right;}
      .hc-msg{margin-bottom:10px;padding:8px 10px;border-radius:8px;line-height:1.5;white-space:pre-wrap;}
      .hc-user{background:#fef3e2;margin-left:30px;}
      .hc-bot{background:#f1f1f1;margin-right:30px;}
      .hc-loading{color:#999;font-style:italic;}
      #hagag-chat-inputrow{display:flex;border-top:1px solid rgba(0,0,0,.08);padding:8px;gap:6px;direction:rtl;}
      #hagag-chat-input{flex:1;border:1px solid #ddd;border-radius:8px;padding:8px;font-size:13px;resize:none;direction:rtl;}
      #hagag-chat-send{background:#d97706;color:#fff;border:none;border-radius:8px;padding:0 14px;cursor:pointer;font-size:13px;}
      #hagag-chat-send:disabled{opacity:.5;cursor:default;}
      .hc-action-btn{display:block;width:100%;margin-top:8px;padding:8px 10px;border:none;border-radius:8px;
        background:#d97706;color:#fff;cursor:pointer;font-size:13px;text-align:center;}
      .hc-action-btn:hover{opacity:.9;}
    `;
    const style = document.createElement("style");
    style.textContent = css;
    document.head.appendChild(style);
  }

  function addMessage(log, text, cls) {
    const div = document.createElement("div");
    div.className = "hc-msg " + cls;
    div.textContent = text;
    log.appendChild(div);
    log.scrollTop = log.scrollHeight;
    return div;
  }

  function buildWidget() {
    const btn = document.createElement("button");
    btn.id = "hagag-chat-btn";
    btn.type = "button";
    btn.innerHTML = "💬";
    document.body.appendChild(btn);

    const panel = document.createElement("div");
    panel.id = "hagag-chat-panel";
    panel.innerHTML = `
      <div id="hagag-chat-header">
        <span>مساعد Hagag</span>
        <span class="close">&times;</span>
      </div>
      <div id="hagag-chat-log"></div>
      <div id="hagag-chat-inputrow">
        <textarea id="hagag-chat-input" rows="1" placeholder="اكتب سؤالك..."></textarea>
        <button id="hagag-chat-send" type="button">إرسال</button>
      </div>
    `;
    document.body.appendChild(panel);

    const log = panel.querySelector("#hagag-chat-log");
    const input = panel.querySelector("#hagag-chat-input");
    const sendBtn = panel.querySelector("#hagag-chat-send");
    const closeBtn = panel.querySelector(".close");

    btn.addEventListener("click", () => panel.classList.toggle("open"));
    closeBtn.addEventListener("click", () => panel.classList.remove("open"));

    function addAction(log, action) {
      if (!action || action.type !== "open") return;
      const routes = {
        journal_entry: "/app/journal-entry/new",
        project: "/app/project/new",
        sales_invoice: "/app/sales-invoice/new",
        customer: "/app/customer/new",
        quotation: "/app/quotation/new",
        task: "/app/task/new"
      };
      const route = routes[action.key];
      if (!route) return;

      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "hc-action-btn";
      btn.textContent = action.label || "فتح";
      btn.addEventListener("click", () => {
        window.location.href = route;
      });

      log.appendChild(btn);
      log.scrollTop = log.scrollHeight;
    }

    function send() {
      const question = input.value.trim();
      if (!question) return;
      addMessage(log, question, "hc-user");
      input.value = "";
      sendBtn.disabled = true;
      const loading = addMessage(log, "بيفكر...", "hc-bot hc-loading");

      frappe.call({
        method: "hagag_erp.api.gemini_gateway.ask_gemini",
        args: { question: question },
        callback: function (r) {
          loading.remove();
          sendBtn.disabled = false;
          if (r.message && r.message.message) {
            addMessage(log, r.message.message, "hc-bot");
            if (r.message.action) {
              addAction(log, r.message.action);
            }
          } else {
            addMessage(log, "معرفتش أجاوب على السؤال ده.", "hc-bot");
          }
        },
        error: function () {
          loading.remove();
          sendBtn.disabled = false;
          addMessage(log, "حصل خطأ في الاتصال. حاول تاني.", "hc-bot");
        }
      });
    }

    sendBtn.addEventListener("click", send);
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        send();
      }
    });
  }

  function init() {
    injectStyles();
    buildWidget();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init, { once: true });
  } else {
    init();
  }
})();
