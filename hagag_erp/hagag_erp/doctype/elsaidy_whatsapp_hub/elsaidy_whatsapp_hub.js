// Copyright (c) 2026, Elsaidy ERP and contributors
// For license information, please see license.txt

frappe.ui.form.on('Elsaidy WhatsApp Hub', {
	refresh: function(frm) {
		frm.trigger('render_dashboard_telemetry');
		frm.trigger('setup_action_buttons');
	},

	// ─── Render Dashboard & Telemetry ──────────────────────────────────────────
	render_dashboard_telemetry: function(frm) {
		frappe.call({
			method: 'hagag_erp.whatsapp_bridge.get_dashboard_telemetry',
			callback: function(r) {
				const data = r.message || {};
				const engineState = (data.engine_state || frm.doc.connection_status || 'DISCONNECTED').toUpperCase();
				const isConnected = data.whatsapp_connected || engineState === 'CONNECTED';
				const isConnecting = engineState === 'CONNECTING';
				const isResetting = engineState === 'RESETTING';
				const phone = data.connected_phone || frm.doc.connected_phone || frm.doc.bot_phone_number || 'غير متصل';
				const botName = data.bot_name || 'Elsaidy WhatsApp Bot';
				const uptimeSec = data.uptime_seconds || 0;
				const uptimeFormatted = frm.events.format_uptime(uptimeSec);
				const metrics = data.today_metrics || {};

				if (isConnected && frm.doc.connection_status !== 'Connected') {
					frm.set_value('connection_status', 'Connected');
				}
				if (data.connected_phone && frm.doc.connected_phone !== data.connected_phone) {
					frm.set_value('connected_phone', data.connected_phone);
				}

				let statusBadge = '';
				let borderColor = '#dc3545';
				let bgColor = '#fff8f8';

				if (isConnected) {
					borderColor = '#28a745';
					bgColor = '#f4fbf6';
					statusBadge = `
						<div style="display:flex; align-items:center; gap:8px;">
							<span style="display:inline-block; width:12px; height:12px; border-radius:50%; background-color:#28a745; box-shadow:0 0 10px rgba(40,167,69,0.8);"></span>
							<strong style="color:#1e7e34; font-size:16px;">متصل بالخدمة (CONNECTED) ✅</strong>
						</div>
					`;
				} else if (isConnecting) {
					borderColor = '#ffc107';
					bgColor = '#fffdf0';
					statusBadge = `
						<div style="display:flex; align-items:center; gap:8px;">
							<span style="display:inline-block; width:12px; height:12px; border-radius:50%; background-color:#ffc107; box-shadow:0 0 10px rgba(255,193,7,0.8);"></span>
							<strong style="color:#d39e00; font-size:16px;">جاري الاتصال... امسح QR أو اطلب الكود 🔄</strong>
						</div>
					`;
				} else if (isResetting) {
					borderColor = '#17a2b8';
					bgColor = '#f0f9fb';
					statusBadge = `
						<div style="display:flex; align-items:center; gap:8px;">
							<span style="display:inline-block; width:12px; height:12px; border-radius:50%; background-color:#17a2b8; box-shadow:0 0 10px rgba(23,162,184,0.8);"></span>
							<strong style="color:#117a8b; font-size:16px;">جاري إعادة ضبط المقبس (RESETTING)... ⚙️</strong>
						</div>
					`;
				} else {
					statusBadge = `
						<div style="display:flex; align-items:center; gap:8px;">
							<span style="display:inline-block; width:12px; height:12px; border-radius:50%; background-color:#dc3545; box-shadow:0 0 10px rgba(220,53,69,0.8);"></span>
							<strong style="color:#bd2130; font-size:16px;">غير متصل (DISCONNECTED) ❌</strong>
						</div>
					`;
				}

				const html = `
					<!-- Top Status Banner -->
					<div style="border: 2px solid ${borderColor}; background-color: ${bgColor}; border-radius: 10px; padding: 18px 22px; margin-bottom: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.04);">
						<div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:12px;">
							<div>
								${statusBadge}
								<div style="margin-top: 8px; color: #495057; font-size: 13px; line-height: 1.6;">
									<strong>الهاتف:</strong> <span dir="ltr" style="font-family:monospace; font-size:14px; color:#212529;">${phone}</span> &nbsp;|&nbsp;
									<strong>اسم البوت:</strong> <span style="color:#212529;">${botName}</span> &nbsp;|&nbsp;
									<strong>مدة تشغيل المحرك:</strong> <span style="color:#212529;">${uptimeFormatted}</span>
								</div>
							</div>
							<div style="display:flex; gap:8px; flex-wrap:wrap;">
								<button type="button" class="btn btn-sm btn-primary" onclick="cur_frm.trigger('open_pairing_dialog')">
									<i class="fa fa-key"></i> ربط برمز الإقران
								</button>
								<button type="button" class="btn btn-sm btn-default" onclick="cur_frm.trigger('open_qr_modal')">
									<i class="fa fa-qrcode"></i> عرض QR Code
								</button>
								<button type="button" class="btn btn-sm btn-default" onclick="cur_frm.trigger('render_dashboard_telemetry')">
									<i class="fa fa-refresh"></i> تحديث القياسات
								</button>
							</div>
						</div>
					</div>

					<!-- Real Telemetry KPI Cards -->
					<div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap:15px; margin-bottom: 22px;">
						<div style="background:#fff; border:1px solid #e2e8f0; border-radius:8px; padding:15px; box-shadow:0 1px 3px rgba(0,0,0,0.04);">
							<div style="font-size:12px; color:#64748b; font-weight:bold;">📥 وارد اليوم</div>
							<div style="font-size:24px; font-weight:bold; color:#0f172a; margin-top:5px;">${metrics.incoming || 0}</div>
							<div style="font-size:11px; color:#94a3b8; margin-top:2px;">رسالة واردة</div>
						</div>
						<div style="background:#fff; border:1px solid #e2e8f0; border-radius:8px; padding:15px; box-shadow:0 1px 3px rgba(0,0,0,0.04);">
							<div style="font-size:12px; color:#64748b; font-weight:bold;">📤 صادر اليوم</div>
							<div style="font-size:24px; font-weight:bold; color:#0284c7; margin-top:5px;">${metrics.replied || 0}</div>
							<div style="font-size:11px; color:#94a3b8; margin-top:2px;">رد تلقائي مرسل</div>
						</div>
						<div style="background:#fff; border:1px solid #e2e8f0; border-radius:8px; padding:15px; box-shadow:0 1px 3px rgba(0,0,0,0.04);">
							<div style="font-size:12px; color:#64748b; font-weight:bold;">🤖 ردود الذكاء الاصطناعي</div>
							<div style="font-size:24px; font-weight:bold; color:#7c3aed; margin-top:5px;">${metrics.ai_replies || 0}</div>
							<div style="font-size:11px; color:#94a3b8; margin-top:2px;">محادثة ذكية اليوم</div>
						</div>
						<div style="background:#fff; border:1px solid #e2e8f0; border-radius:8px; padding:15px; box-shadow:0 1px 3px rgba(0,0,0,0.04);">
							<div style="font-size:12px; color:#64748b; font-weight:bold;">📝 قيود ZATCA اليوم</div>
							<div style="font-size:24px; font-weight:bold; color:#16a34a; margin-top:5px;">${metrics.expenses_processed || 0}</div>
							<div style="font-size:11px; color:#94a3b8; margin-top:2px;">مصروف معتمد كمسودة</div>
						</div>
						<div style="background:#fff; border:1px solid #e2e8f0; border-radius:8px; padding:15px; box-shadow:0 1px 3px rgba(0,0,0,0.04);">
							<div style="font-size:12px; color:#64748b; font-weight:bold;">⚠️ أخطاء اليوم</div>
							<div style="font-size:24px; font-weight:bold; color:#dc2626; margin-top:5px;">${metrics.failed || 0}</div>
							<div style="font-size:11px; color:#94a3b8; margin-top:2px;">فشل في المعالجة</div>
						</div>
					</div>
				`;

				frm.set_df_property('status_html', 'options', html);
				frm.refresh_field('status_html');
			}
		});
	},

	format_uptime: function(seconds) {
		if (!seconds || seconds <= 0) return '0 ثانية';
		const d = Math.floor(seconds / 86400);
		const h = Math.floor((seconds % 86400) / 3600);
		const m = Math.floor((seconds % 3600) / 60);
		const s = seconds % 60;
		let str = '';
		if (d > 0) str += `${d} يوم `;
		if (h > 0) str += `${h} س `;
		if (m > 0) str += `${m} د `;
		if (s > 0 && d === 0) str += `${s} ث`;
		return str.trim() || 'ثوانٍ معدودة';
	},

	// ─── Setup Action Buttons ──────────────────────────────────────────────────
	setup_action_buttons: function(frm) {
		frm.page.clear_actions();

		// ── Connection Group ──────────────────────────────────────────────────
		frm.add_custom_button(__('طلب كود الإقران'), function() {
			frm.trigger('open_pairing_dialog');
		}, __('اتصال واتساب'));

		frm.add_custom_button(__('عرض QR Code'), function() {
			frm.trigger('open_qr_modal');
		}, __('اتصال واتساب'));

		// ── Maintenance & Healing Group ───────────────────────────────────────
		frm.add_custom_button(__('🩺 تشخيص وإصلاح Bad MAC الموجه'), function() {
			frm.trigger('open_heal_dialog');
		}, __('صيانة الجلسة'));

		frm.add_custom_button(__('🔄 إعادة تشغيل المحرك'), function() {
			frm.trigger('restart_engine_action');
		}, __('صيانة الجلسة'));

		frm.add_custom_button(__('🧹 تطهير الجلسة بالكامل (Hard Reset)'), function() {
			frm.trigger('wipe_session_action');
		}, __('صيانة الجلسة'));

		// ── Tools & Diagnostics Group ─────────────────────────────────────────
		frm.add_custom_button(__('🧪 محاكي الذكاء الاصطناعي (Dry Run)'), function() {
			frm.trigger('open_ai_simulator_dialog');
		}, __('أدوات واختبارات'));

		frm.add_custom_button(__('📤 إرسال رسالة تجريبية'), function() {
			frm.trigger('open_test_message_dialog');
		}, __('أدوات واختبارات'));

		frm.add_custom_button(__('📋 سجلات السيرفر الحية'), function() {
			frm.trigger('show_live_logs');
		}, __('أدوات واختبارات'));

		frm.add_custom_button(__('👥 جلب مجموعاتي الحالية'), function() {
			frm.trigger('fetch_groups_action');
		}, __('أدوات واختبارات'));

		// ── Top Level ─────────────────────────────────────────────────────────
		frm.add_custom_button(__('تحديث الحالة'), function() {
			frm.trigger('render_dashboard_telemetry');
		});
	},

	// ─── Heal Bad MAC Dialog ───────────────────────────────────────────────────
	open_heal_dialog: function(frm) {
		const d = new frappe.ui.Dialog({
			title: __('🩺 نظام التشخيص والإصلاح الذاتي لـ Bad MAC'),
			fields: [
				{
					fieldname: 'target',
					fieldtype: 'Data',
					label: __('رقم الهاتف أو المعرف المستهدف (Target JID / Phone)'),
					reqd: 1,
					default: frm.doc.connected_phone || frm.doc.bot_phone_number || '',
					description: __('أدخل رقم الهاتف أو معرف الجلسة مثل: 251036744843464.0 أو 966569589664 أو 120363...@g.us')
				},
				{
					fieldtype: 'HTML',
					fieldname: 'heal_info',
					options: `
						<div style="background:#eef6ff; border:1px solid #bfdbfe; border-radius:6px; padding:12px; margin-top:8px; font-size:12px; color:#1e40af; line-height:1.5;">
							💡 <strong>آلية الإصلاح الموجه:</strong><br>
							• يقوم النظام بحذف ملف المفتاح المتضرر فقط (مثل <code>session-...</code> أو <code>sender-key-...</code>).<br>
							• <strong>لا يتم المساس</strong> بملف <code>creds.json</code> أو بيانات الربط الأساسية.<br>
							• يستدعي المحرك دالة <code>assertSessions</code> لجلب مفاتيح PreKeys جديدة من خوادم واتساب فوراً.
						</div>
					`
				}
			],
			primary_action_label: __('بدء الفحص والإصلاح الموجه'),
			primary_action: function(values) {
				d.hide();
				frappe.call({
					method: 'hagag_erp.whatsapp_bridge.heal_baileys_session',
					args: { target: values.target },
					freeze: true,
					freeze_message: __('جاري فحص وإصلاح الجلسة الموجهة...'),
					callback: function(r) {
						const res = r.message || {};
						if (res.status === 'ok') {
							frappe.msgprint({
								title: __('✅ نجاح عملية الإصلاح الموجه'),
								indicator: 'green',
								message: `<strong>النتيجة:</strong> ${res.message}<br>` +
									`<strong>الملفات المحذوفة:</strong> ${res.deleted_files_count || 0}<br>` +
									`<strong>إعادة جلب المفاتيح:</strong> ${res.session_reasserted ? 'نعم (PreKeys Updated)' : 'تم الحذف وتنتظر الاتصال'}`
							});
							frm.trigger('render_dashboard_telemetry');
						} else {
							frappe.msgprint({
								title: __('تنبيه في الإصلاح'),
								indicator: 'orange',
								message: res.message || res.error || __('فشلت العملية')
							});
						}
					}
				});
			}
		});
		d.show();
	},

	// ─── AI Simulator Dialog (Dry Run Mode) ───────────────────────────────────
	open_ai_simulator_dialog: function(frm) {
		const simDialog = new frappe.ui.Dialog({
			title: __('🧪 محاكي الذكاء الاصطناعي (AI Simulator & Dry Run)'),
			size: 'large',
			fields: [
				{
					fieldname: 'text',
					fieldtype: 'Small Text',
					label: __('نص الرسالة المراد اختبارها'),
					reqd: 1,
					default: 'صرفت 500 ريال وقود ديزل لموقع الرياض'
				},
				{
					fieldname: 'sender_phone',
					fieldtype: 'Data',
					label: __('رقم هاتف المرسل المفترض'),
					default: frm.doc.connected_phone || '966569589664'
				},
				{
					fieldtype: 'Section Break',
					label: __('نتائج المحاكاة (JSON & Preview)')
				},
				{
					fieldname: 'sim_result_html',
					fieldtype: 'HTML',
					options: `<div style="color:#64748b; font-style:italic; padding:15px; text-align:center;">اضغط على "تشغيل المحاكاة" بالأسفل لمعاينة المعالجة والرد دون حفظ في قاعدة البيانات.</div>`
				}
			],
			primary_action_label: __('🚀 تشغيل المحاكاة (Dry Run)'),
			primary_action: function(values) {
				frappe.call({
					method: 'hagag_erp.whatsapp_bridge.simulate_whatsapp_message',
					args: {
						text: values.text,
						sender_phone: values.sender_phone
					},
					freeze: true,
					freeze_message: __('جاري تشغيل المحاكاة وفك القصد المحاسبي...'),
					callback: function(r) {
						const res = r.message || {};
						if (res.status === 'ok') {
							let entitiesHtml = '';
							if (res.parsed_entities && res.parsed_entities.amount) {
								entitiesHtml = `
									<table class="table table-bordered table-condensed" style="margin-top:10px; font-size:12px;">
										<tr style="background:#f8fafc;">
											<th>المبلغ الإجمالي</th>
											<th>صافي قبل الضريبة</th>
											<th>ضريبة 15% ZATCA</th>
											<th>المورد / الجهة</th>
										</tr>
										<tr>
											<td><strong style="color:#16a34a;">${res.parsed_entities.total_amount} ر.س</strong></td>
											<td>${res.parsed_entities.net_amount} ر.س</td>
											<td>${res.parsed_entities.tax_amount} ر.س</td>
											<td>${res.parsed_entities.vendor}</td>
										</tr>
									</table>
								`;
							}

							const previewHtml = `
								<div style="background:#f8fafc; border:1px solid #e2e8f0; border-radius:8px; padding:15px;">
									<div style="display:flex; justify-content:space-between; align-items:center;">
										<span class="badge badge-success" style="font-size:13px; padding:5px 10px;">
											القصد المكتشف: ${res.detected_intent}
										</span>
										<span style="font-size:11px; color:#64748b; font-weight:bold;">${res.mode}</span>
									</div>
									${entitiesHtml}
									<div style="margin-top:15px;">
										<strong style="font-size:13px; color:#334155;">💬 الرد المتوقع إرساله للعميل عبر WhatsApp:</strong>
										<div style="background:#fff; border:1px solid #cbd5e1; border-radius:8px; padding:12px; margin-top:6px; white-space:pre-wrap; font-family:inherit; font-size:13px; color:#0f172a; line-height:1.6;">
${res.simulated_reply}
										</div>
									</div>
								</div>
							`;
							simDialog.set_value('sim_result_html', previewHtml);
						} else {
							simDialog.set_value('sim_result_html', `<div class="alert alert-danger">${res.message || 'خطأ في المحاكاة'}</div>`);
						}
					}
				});
			}
		});
		simDialog.show();
	},

	// ─── Live Logs Viewer ──────────────────────────────────────────────────────
	show_live_logs: function(frm) {
		let logsInterval = null;

		const logsDialog = new frappe.ui.Dialog({
			title: __('📋 سجلات سيرفر Baileys الحية (Live Console)'),
			size: 'large',
			fields: [
				{
					fieldname: 'sec_filters',
					fieldtype: 'Section Break'
				},
				{
					fieldname: 'level_filter',
					fieldtype: 'Select',
					label: __('المستوى'),
					options: 'ALL\nINFO\nWARN\nERROR',
					default: 'ALL'
				},
				{
					fieldname: 'col_break_1',
					fieldtype: 'Column Break'
				},
				{
					fieldname: 'search_filter',
					fieldtype: 'Data',
					label: __('بحث بالكلمة المفتاحية')
				},
				{
					fieldname: 'col_break_2',
					fieldtype: 'Column Break'
				},
				{
					fieldname: 'auto_refresh',
					fieldtype: 'Check',
					label: __('تحديث حي تلقائي (كل 3 ثوان)'),
					default: 1
				},
				{
					fieldname: 'sec_logs_table',
					fieldtype: 'Section Break'
				},
				{
					fieldname: 'logs_html',
					fieldtype: 'HTML'
				}
			],
			primary_action_label: __('🔄 تحديث فوري'),
			primary_action: function() {
				fetch_logs();
			},
			secondary_action_label: __('مسح العرض'),
			secondary_action: function() {
				logsDialog.set_value('logs_html', '<div style="padding:15px; text-align:center; color:#94a3b8;">تم مسح نافذة العرض. اضغط تحديث لاسترجاع السجلات.</div>');
			}
		});

		function fetch_logs() {
			const level = logsDialog.get_value('level_filter');
			const search = logsDialog.get_value('search_filter') || '';

			frappe.call({
				method: 'hagag_erp.whatsapp_bridge.get_baileys_logs',
				args: {
					limit: 100,
					level: level === 'ALL' ? '' : level,
					search: search
				},
				callback: function(r) {
					const data = r.message || {};
					const logs = data.logs || [];

					if (logs.length === 0) {
						logsDialog.set_value('logs_html', '<div style="padding:20px; text-align:center; color:#94a3b8;">لا توجد سجلات تطابق الفلتر الحالي.</div>');
						return;
					}

					let rows = logs.map(e => {
						const color = e.level === 'error' ? '#ef4444' : (e.level === 'warn' ? '#f59e0b' : '#10b981');
						return `
							<tr>
								<td style="white-space:nowrap; font-size:11px; color:#64748b;">${e.ts ? e.ts.split('T')[1].split('.')[0] : ''}</td>
								<td style="text-align:center;">
									<span style="background:${color}; color:#fff; border-radius:3px; padding:2px 6px; font-size:10px; font-weight:bold;">
										${(e.level || 'info').toUpperCase()}
									</span>
								</td>
								<td style="font-family:monospace; font-size:12px; word-break:break-word; color:#1e293b;">
									${frappe.utils.escape_html(e.msg || '')}
								</td>
							</tr>
						`;
					}).join('');

					const tableHtml = `
						<div style="margin-bottom:8px; font-size:12px; color:#64748b;">
							عرض <strong>${logs.length}</strong> سجل (إجمالي الذاكرة: ${data.total_buffered || logs.length})
						</div>
						<div style="max-height:380px; overflow-y:auto; border:1px solid #e2e8f0; border-radius:6px;">
							<table class="table table-hover table-condensed" style="margin:0;">
								<thead style="background:#f8fafc; position:sticky; top:0;">
									<tr>
										<th style="width:100px;">التوقيت</th>
										<th style="width:70px;">النوع</th>
										<th>الرسالة</th>
									</tr>
								</thead>
								<tbody>${rows}</tbody>
							</table>
						</div>
					`;
					logsDialog.set_value('logs_html', tableHtml);
				}
			});
		}

		logsDialog.fields_dict.level_filter.$input.on('change', fetch_logs);
		logsDialog.fields_dict.search_filter.$input.on('keyup', frappe.utils.debounce(fetch_logs, 300));

		logsDialog.on_page_show = function() {
			fetch_logs();
			logsInterval = setInterval(() => {
				if (logsDialog.$wrapper.is(':visible') && logsDialog.get_value('auto_refresh')) {
					fetch_logs();
				}
			}, 3000);
		};

		logsDialog.on_hide = function() {
			if (logsInterval) clearInterval(logsInterval);
		};

		logsDialog.show();
	},

	// ─── Pairing Dialog ────────────────────────────────────────────────────────
	open_pairing_dialog: function(frm) {
		const d = new frappe.ui.Dialog({
			title: __('ربط واتساب برمز الإقران (Pairing Code) 🔑'),
			fields: [
				{
					fieldname: 'phone',
					fieldtype: 'Data',
					label: __('رقم الهاتف (مع كود الدولة)'),
					reqd: 1,
					default: frm.doc.bot_phone_number || '',
					description: __('مثال: 01028632620 أو 966569589664')
				},
				{
					fieldtype: 'HTML',
					fieldname: 'pair_hint',
					options: `<div style="background:#fff3cd; border:1px solid #ffc107; border-radius:5px; padding:10px; margin-top:8px; font-size:13px;">
						⚠️ <strong>ملاحظة:</strong> سيتم تنظيف مفاتيح الجلسة القديمة وإعادة التهيئة لتوليد كود نقي.<br>
						افتح واتساب على هاتفك ← إعدادات ← الأجهزة المرتبطة ← ربط جهاز ← إدخال الكود يدوياً.
					</div>`
				}
			],
			primary_action_label: __('🔑 إنشاء كود الإقران'),
			primary_action: function(values) {
				d.hide();
				frappe.call({
					method: 'request_pairing',
					doc: frm.doc,
					args: { phone: values.phone },
					freeze: true,
					freeze_message: __('جاري إنشاء كود الإقران...'),
					callback: function(r) {
						if (r.message && r.message.status === 'ok') {
							const code = r.message.formatted_code || r.message.code;
							const codeDialog = new frappe.ui.Dialog({
								title: __('✅ كود الإقران جاهز!'),
								fields: [
									{
										fieldtype: 'HTML',
										fieldname: 'code_html',
										options: `
											<div style="text-align:center; padding:20px;">
												<p style="font-size:14px; color:#495057; margin-bottom:15px;">
													أدخل هذا الكود في واتساب على هاتفك خلال <strong>60 ثانية</strong>:
												</p>
												<div style="font-size:42px; font-weight:bold; font-family:monospace; letter-spacing:8px; color:#25d366; background:#f0fff4; border:2px dashed #25d366; border-radius:10px; padding:20px 30px; display:inline-block;">
													${code}
												</div>
												<p style="font-size:12px; color:#6c757d; margin-top:15px;">
													واتساب ← إعدادات ← الأجهزة المرتبطة ← ربط جهاز ← إدخال الكود يدوياً
												</p>
											</div>
										`
									}
								],
								primary_action_label: __('✅ تم — تحقق من الاتصال'),
								primary_action: function() {
									codeDialog.hide();
									setTimeout(() => frm.trigger('render_dashboard_telemetry'), 3000);
								}
							});
							codeDialog.show();
						} else if (r.message && r.message.status === 'already_connected') {
							frappe.msgprint(__('واتساب متصل مسبقاً برقم: ' + r.message.bot_phone));
						} else {
							frappe.msgprint(__('فشل إنشاء كود الإقران. تحقق من السجلات.'));
						}
					}
				});
			}
		});
		d.show();
	},

	// ─── QR Modal ──────────────────────────────────────────────────────────────
	open_qr_modal: function(frm) {
		frappe.call({
			method: 'get_qr',
			doc: frm.doc,
			freeze: true,
			freeze_message: __('جاري جلب صورة QR الحالية...'),
			callback: function(r) {
				if (r.message && r.message.qr_data_url) {
					const qrDialog = new frappe.ui.Dialog({
						title: __('امسح كود QR لربط واتساب 📱'),
						fields: [
							{
								fieldtype: 'HTML',
								fieldname: 'qr_html',
								options: `
									<div style="text-align:center; padding:15px;">
										<img src="${r.message.qr_data_url}" alt="WhatsApp QR Code" style="max-width:260px; border-radius:8px; box-shadow:0 2px 10px rgba(0,0,0,0.15); margin-bottom:15px;" />
										<p style="font-size:13px; color:#6c757d;">واتساب ← إعدادات ← الأجهزة المرتبطة ← ربط جهاز</p>
									</div>
								`
							}
						],
						primary_action_label: __('🔄 تحديث QR'),
						primary_action: function() {
							qrDialog.hide();
							frm.trigger('open_qr_modal');
						}
					});
					qrDialog.show();
				} else if (r.message && r.message.status === 'already_connected') {
					frappe.msgprint(__('واتساب متصل مسبقاً برقم: ' + r.message.bot_phone));
				} else {
					frappe.msgprint(__('لا يوجد QR Code حالياً. جاري تهيئة الاتصال أو يمكنك استخدام Pairing Code.'));
				}
			}
		});
	},

	// ─── Fetch Groups Action ──────────────────────────────────────────────────
	fetch_groups_action: function(frm) {
		frappe.call({
			method: 'sync_groups',
			doc: frm.doc,
			freeze: true,
			freeze_message: __('جاري جلب المجموعات من Baileys...'),
			callback: function(r) {
				frm.reload_doc();
				if (r.message && r.message.status === 'ok') {
					frappe.msgprint({
						title: __('✅ تمت مزامنة المجموعات'),
						indicator: 'green',
						message: __('تم إضافة وتحديث ' + (r.message.count || 0) + ' مجموعة في القائمة.')
					});
				}
			}
		});
	},

	// ─── Restart Engine Action ────────────────────────────────────────────────
	restart_engine_action: function(frm) {
		frappe.confirm(__('هل تريد إعادة تشغيل مقبس Baileys بأمان دون مسح الجلسة؟'), function() {
			frappe.call({
				method: 'restart_service',
				doc: frm.doc,
				freeze: true,
				freeze_message: __('جاري إعادة تشغيل المحرك...'),
				callback: function(r) {
					if (r.message && r.message.status === 'ok') {
						frappe.show_alert({ message: __('تمت إعادة التشغيل بنجاح.'), indicator: 'green' });
						setTimeout(() => frm.trigger('render_dashboard_telemetry'), 2500);
					}
				}
			});
		});
	},

	// ─── Wipe Session Action ──────────────────────────────────────────────────
	wipe_session_action: function(frm) {
		frappe.confirm(
			__('⚠️ تحذير: سيتم مسح جلسة واتساب بالكامل وإلغاء الربط.\n\nهل أنت متأكد؟'),
			function() {
				frappe.call({
					method: 'hagag_erp.whatsapp_bridge.wipe_baileys_session',
					freeze: true,
					freeze_message: __('جاري مسح الجلسة بالكامل...'),
					callback: function(r) {
						frm.reload_doc();
						if (r.message && r.message.status === 'ok') {
							frappe.msgprint({
								title: __('تم تطهير الجلسة'),
								indicator: 'blue',
								message: __('تم مسح الجلسة بنجاح. يمكنك الآن إعادة الربط بكود إقران أو QR.')
							});
							setTimeout(() => frm.trigger('render_dashboard_telemetry'), 3000);
						}
					}
				});
			}
		);
	},

	// ─── Test Message Dialog ──────────────────────────────────────────────────
	open_test_message_dialog: function(frm) {
		const d = new frappe.ui.Dialog({
			title: __('إرسال رسالة تجريبية 📤'),
			fields: [
				{
					fieldname: 'recipient',
					fieldtype: 'Data',
					label: __('رقم الهاتف أو JID المجموعة'),
					reqd: 1,
					default: frm.doc.connected_phone || '',
					description: __('مثال: 01028632620 أو 966569589664 أو JID مجموعة')
				},
				{
					fieldname: 'message',
					fieldtype: 'Small Text',
					label: __('نص الرسالة'),
					reqd: 1,
					default: 'مرحباً من نظام Elsaidy WhatsApp Hub Enterprise ✅'
				}
			],
			primary_action_label: __('إرسال الرسالة'),
			primary_action: function(values) {
				d.hide();
				frappe.call({
					method: 'hagag_erp.whatsapp_bridge.send_test_whatsapp_message',
					args: {
						recipient: values.recipient,
						message: values.message
					},
					freeze: true,
					freeze_message: __('جاري إرسال الرسالة...'),
					callback: function(r) {
						if (r.message && r.message.status === 'ok') {
							frappe.show_alert({ message: __('✅ تم إرسال الرسالة بنجاح!'), indicator: 'green' });
							frm.trigger('render_dashboard_telemetry');
						} else {
							frappe.msgprint(__('فشل الإرسال: ' + (r.message ? r.message.error : 'لا يوجد رد')));
						}
					}
				});
			}
		});
		d.show();
	}
});
