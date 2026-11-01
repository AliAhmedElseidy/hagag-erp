// Copyright (c) 2026, Elsaidy ERP and contributors
// For license information, please see license.txt

frappe.ui.form.on('Elsaidy WhatsApp Hub', {
	refresh: function(frm) {
		frm.trigger('render_status_banner');
		frm.trigger('setup_action_buttons');
	},

	render_status_banner: function(frm) {
		const isConnected = frm.doc.connection_status === 'Connected';
		const isConnecting = frm.doc.connection_status === 'Connecting';
		const phone = frm.doc.connected_phone || frm.doc.bot_phone_number || 'غير متصل';
		const syncTime = frm.doc.last_sync_time || 'لم تتم مزامنة بعد';

		let statusBadge = '';
		let borderColor = '#dc3545';
		let bgColor = '#fff5f5';

		if (isConnected) {
			borderColor = '#28a745';
			bgColor = '#f4fbf6';
			statusBadge = `
				<div style="display:flex; align-items:center; gap:8px;">
					<span style="display:inline-block; width:14px; height:14px; border-radius:50%; background-color:#28a745; box-shadow:0 0 8px rgba(40,167,69,0.6);"></span>
					<strong style="color:#1e7e34; font-size:16px;">متصل بنجاح ✅</strong>
				</div>
			`;
		} else if (isConnecting) {
			borderColor = '#ffc107';
			bgColor = '#fffdf0';
			statusBadge = `
				<div style="display:flex; align-items:center; gap:8px;">
					<span style="display:inline-block; width:14px; height:14px; border-radius:50%; background-color:#ffc107; box-shadow:0 0 8px rgba(255,193,7,0.6);"></span>
					<strong style="color:#d39e00; font-size:16px;">جاري الاتصال... امسح QR 🔄</strong>
				</div>
			`;
		} else {
			statusBadge = `
				<div style="display:flex; align-items:center; gap:8px;">
					<span style="display:inline-block; width:14px; height:14px; border-radius:50%; background-color:#dc3545; box-shadow:0 0 8px rgba(220,53,69,0.6);"></span>
					<strong style="color:#bd2130; font-size:16px;">غير متصل - اضغط ربط الجلسة ❌</strong>
				</div>
			`;
		}

		const html = `
			<div style="border: 2px solid ${borderColor}; background-color: ${bgColor}; border-radius: 10px; padding: 18px 22px; margin-bottom: 15px; box-shadow: 0 2px 6px rgba(0,0,0,0.04);">
				<div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:12px;">
					<div>
						${statusBadge}
						<div style="margin-top: 8px; color: #495057; font-size: 13px;">
							<strong>الهاتف المتصل:</strong> <span dir="ltr" style="font-family:monospace; font-size:14px;">${phone}</span> &nbsp;|&nbsp;
							<strong>آخر مزامنة:</strong> ${syncTime}
						</div>
					</div>
					<div style="display:flex; gap:8px; flex-wrap:wrap;">
						<button type="button" class="btn btn-sm btn-primary" onclick="cur_frm.trigger('open_pairing_dialog')">
							<i class="fa fa-key"></i> ربط برمز الإقران (Pairing Code)
						</button>
						<button type="button" class="btn btn-sm btn-default" onclick="cur_frm.trigger('open_qr_modal')">
							<i class="fa fa-qrcode"></i> عرض QR Code
						</button>
						<button type="button" class="btn btn-sm btn-default" onclick="cur_frm.trigger('check_status')">
							<i class="fa fa-refresh"></i> تحديث الحالة
						</button>
					</div>
				</div>
			</div>
		`;

		frm.set_df_property('status_html', 'options', html);
		frm.refresh_field('status_html');
	},

	setup_action_buttons: function(frm) {
		frm.page.clear_actions();

		// ── Connection Group ──────────────────────────────────────────────────
		frm.add_custom_button(__('ربط برمز الإقران'), function() {
			frm.trigger('open_pairing_dialog');
		}, __('اتصال واتساب'));

		frm.add_custom_button(__('عرض QR Code'), function() {
			frm.trigger('open_qr_modal');
		}, __('اتصال واتساب'));

		// ── Session/Fix Group ─────────────────────────────────────────────────
		frm.add_custom_button(__('🧹 تطهير الجلسة وإصلاح التشفير'), function() {
			frm.trigger('wipe_session_action');
		}, __('صيانة الجلسة'));

		frm.add_custom_button(__('📋 سجلات السيرفر الحية'), function() {
			frm.trigger('show_live_logs');
		}, __('صيانة الجلسة'));

		// ── Data Group ────────────────────────────────────────────────────────
		frm.add_custom_button(__('جلب مجموعاتي الحالية'), function() {
			frm.trigger('fetch_groups_action');
		}, __('البيانات'));

		frm.add_custom_button(__('إرسال رسالة تجريبية'), function() {
			frm.trigger('open_test_message_dialog');
		}, __('البيانات'));

		// ── Top-level ─────────────────────────────────────────────────────────
		frm.add_custom_button(__('تحديث الحالة'), function() {
			frm.trigger('check_status');
		});

		// ── Menu items ────────────────────────────────────────────────────────
		frm.page.add_menu_item(__('إعادة تشغيل الخدمة'), function() {
			frappe.confirm(__('هل تريد إعادة تشغيل خدمة واتساب دون مسح الجلسة؟'), function() {
				frappe.call({
					method: 'restart_service',
					doc: frm.doc,
					freeze: true,
					freeze_message: __('جاري إعادة تشغيل خدمة Baileys...'),
					callback: function(r) {
						if (r.message && r.message.status === 'ok') {
							frappe.show_alert({ message: __('تمت إعادة التشغيل بنجاح.'), indicator: 'green' });
						}
					}
				});
			});
		});

		frm.page.add_menu_item(__('تسجيل الخروج وإلغاء الربط'), function() {
			frappe.confirm(__('⚠️ هل أنت متأكد من تسجيل الخروج ومسح جلسة واتساب نهائياً؟'), function() {
				frappe.call({
					method: 'logout_service',
					doc: frm.doc,
					freeze: true,
					freeze_message: __('جاري تسجيل الخروج...'),
					callback: function(r) {
						frm.reload_doc();
						if (r.message && r.message.status === 'ok') {
							frappe.show_alert({ message: __('تم تسجيل الخروج بنجاح.'), indicator: 'blue' });
						}
					}
				});
			});
		});
	},

	// ── Check Status ──────────────────────────────────────────────────────────
	check_status: function(frm) {
		frappe.call({
			method: 'refresh_status',
			doc: frm.doc,
			freeze: true,
			freeze_message: __('جاري استعلام حالة الاتصال...'),
			callback: function(r) {
				frm.reload_doc();
				if (r.message) {
					const st = r.message.status || 'Unknown';
					const indicator = st === 'Connected' ? 'green' : (st === 'Connecting' ? 'yellow' : 'red');
					frappe.show_alert({ message: __('الحالة: ') + st, indicator: indicator });
				}
			}
		});
	},

	// ── Wipe Session (Hard Reset / Fix Bad MAC) ───────────────────────────────
	wipe_session_action: function(frm) {
		frappe.confirm(
			__('⚠️ سيتم مسح جلسة واتساب بالكامل وإعادة تهيئتها لحل مشاكل التشفير (Bad MAC / 401).\n\nستحتاج إلى إعادة ربط الجهاز بعد ذلك.\n\nهل تريد المتابعة؟'),
			function() {
				frappe.call({
					method: 'hagag_erp.whatsapp_bridge.wipe_baileys_session',
					freeze: true,
					freeze_message: __('🧹 جاري مسح الجلسة وإعادة التهيئة...'),
					callback: function(r) {
						frm.reload_doc();
						if (r.message && r.message.status === 'ok') {
							frappe.msgprint({
								title: __('✅ تم تطهير الجلسة بنجاح'),
								indicator: 'green',
								message: __('تم مسح جلسة واتساب وإعادة تهيئة المقبس.<br>'
									+ 'الرجاء الانتظار 3 ثوان ثم استخدام <strong>ربط برمز الإقران</strong> أو <strong>عرض QR Code</strong> لإعادة الاتصال.')
							});
							setTimeout(() => frm.trigger('check_status'), 5000);
						} else {
							frappe.msgprint({
								title: __('خطأ'),
								indicator: 'red',
								message: __('فشل تطهير الجلسة: ') + JSON.stringify(r.message || r.exc || 'خطأ غير معروف')
							});
						}
					}
				});
			}
		);
	},

	// ── Live Logs Dialog ──────────────────────────────────────────────────────
	show_live_logs: function(frm) {
		frappe.call({
			method: 'hagag_erp.whatsapp_bridge.get_baileys_logs',
			args: { limit: 100 },
			freeze: true,
			freeze_message: __('جاري جلب سجلات السيرفر...'),
			callback: function(r) {
				const data = r.message || {};
				const logs = data.logs || [];

				if (logs.length === 0) {
					frappe.msgprint(__('لا توجد سجلات متاحة في الذاكرة حالياً.'));
					return;
				}

				// Build HTML table
				let tableRows = logs.map(entry => {
					const levelColor = entry.level === 'error' ? '#dc3545'
						: entry.level === 'warn' ? '#ffc107' : '#28a745';
					const escapedMsg = frappe.utils.escape_html(entry.msg || '');
					return `<tr>
						<td style="font-size:11px; color:#6c757d; white-space:nowrap;">${entry.ts || ''}</td>
						<td style="text-align:center;">
							<span style="background:${levelColor}; color:#fff; border-radius:3px; padding:1px 6px; font-size:10px; font-weight:bold;">
								${(entry.level || 'info').toUpperCase()}
							</span>
						</td>
						<td style="font-family:monospace; font-size:12px; word-break:break-word;">${escapedMsg}</td>
					</tr>`;
				}).join('');

				const logsHtml = `
					<div style="margin-bottom:10px; color:#6c757d; font-size:12px;">
						📊 عرض آخر <strong>${logs.length}</strong> سجل (أحدث أولاً) — الإجمالي في الذاكرة: ${data.total_buffered || logs.length}
					</div>
					<div style="max-height:400px; overflow-y:auto; border:1px solid #dee2e6; border-radius:4px;">
						<table class="table table-condensed table-hover" style="margin:0; font-size:12px;">
							<thead style="background:#f8f9fa; position:sticky; top:0;">
								<tr>
									<th style="width:180px;">التوقيت</th>
									<th style="width:60px;">المستوى</th>
									<th>الرسالة</th>
								</tr>
							</thead>
							<tbody>${tableRows}</tbody>
						</table>
					</div>
				`;

				const logsDialog = new frappe.ui.Dialog({
					title: __('📋 سجلات سيرفر Baileys الحية'),
					fields: [
						{
							fieldtype: 'HTML',
							fieldname: 'logs_html',
							options: logsHtml
						}
					],
					primary_action_label: __('🔄 تحديث'),
					primary_action: function() {
						logsDialog.hide();
						frm.trigger('show_live_logs');
					},
					secondary_action_label: __('إغلاق'),
					secondary_action: function() {
						logsDialog.hide();
					}
				});
				logsDialog.show();
			}
		});
	},

	// ── Pairing Dialog ────────────────────────────────────────────────────────
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
					description: __('مثال: 01028632620 أو 966501234567 — سيُحوَّل تلقائياً')
				},
				{
					fieldtype: 'HTML',
					fieldname: 'pair_hint',
					options: `<div style="background:#fff3cd; border:1px solid #ffc107; border-radius:5px; padding:10px; margin-top:8px; font-size:13px;">
						⚠️ <strong>ملاحظة:</strong> سيتم مسح الجلسة الحالية وإعادة تهيئتها قبل إنشاء الكود. 
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
					freeze_message: __('جاري مسح الجلسة وإنشاء كود الإقران...'),
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
									setTimeout(() => frm.trigger('check_status'), 3000);
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

	// ── QR Modal ──────────────────────────────────────────────────────────────
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
					frappe.msgprint(__('لا يوجد QR code حالياً. استخدم Pairing Code أو أعد تشغيل الخدمة.'));
				}
			}
		});
	},

	// ── Fetch Groups ──────────────────────────────────────────────────────────
	fetch_groups_action: function(frm) {
		frappe.call({
			method: 'sync_groups',
			doc: frm.doc,
			freeze: true,
			freeze_message: __('جاري جلب قائمة المجموعات من Baileys...'),
			callback: function(r) {
				frm.reload_doc();
				if (r.message && r.message.status === 'ok') {
					frappe.msgprint({
						title: __('✅ تمت مزامنة المجموعات'),
						indicator: 'green',
						message: __('تم إضافة ' + (r.message.count || 0) + ' مجموعة إلى القائمة.')
					});
				}
			}
		});
	},

	// ── Test Message Dialog ───────────────────────────────────────────────────
	open_test_message_dialog: function(frm) {
		const d = new frappe.ui.Dialog({
			title: __('إرسال رسالة تجريبية 📤'),
			fields: [
				{
					fieldname: 'recipient',
					fieldtype: 'Data',
					label: __('رقم الهاتف أو JID المجموعة'),
					reqd: 1,
					description: __('مثال: 01028632620 أو مجموعة 120363...@g.us')
				},
				{
					fieldname: 'message',
					fieldtype: 'Small Text',
					label: __('نص الرسالة'),
					reqd: 1,
					default: 'مرحباً من نظام Elsaidy ERP — Elsaidy WhatsApp Hub ✅'
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
					freeze_message: __('جاري إرسال الرسالة التجريبية...'),
					callback: function(r) {
						if (r.message && r.message.status === 'ok') {
							frappe.show_alert({ message: __('✅ تم إرسال الرسالة بنجاح!'), indicator: 'green' });
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
