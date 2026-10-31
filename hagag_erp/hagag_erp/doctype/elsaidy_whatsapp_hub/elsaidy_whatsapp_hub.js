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
		const phone = frm.doc.connected_phone || frm.doc.bot_phone_number || 'غير محدد';
		const syncTime = frm.doc.last_sync_time || 'لم يتم الفحص بعد';

		let statusBadge = '';
		let borderColor = '#dc3545';
		let bgColor = '#fff5f5';

		if (isConnected) {
			borderColor = '#28a745';
			bgColor = '#f4fbf6';
			statusBadge = `
				<div style="display:flex; align-items:center; gap:8px;">
					<span style="display:inline-block; width:14px; height:14px; border-radius:50%; background-color:#28a745; box-shadow:0 0 8px rgba(40,167,69,0.6);"></span>
					<strong style="color:#1e7e34; font-size:16px;">متصل وجاهز للخدمة 🟢</strong>
				</div>
			`;
		} else if (isConnecting) {
			borderColor = '#ffc107';
			bgColor = '#fffdf0';
			statusBadge = `
				<div style="display:flex; align-items:center; gap:8px;">
					<span style="display:inline-block; width:14px; height:14px; border-radius:50%; background-color:#ffc107; box-shadow:0 0 8px rgba(255,193,7,0.6);"></span>
					<strong style="color:#d39e00; font-size:16px;">جاري الاتصال والتهيئة 🟡</strong>
				</div>
			`;
		} else {
			statusBadge = `
				<div style="display:flex; align-items:center; gap:8px;">
					<span style="display:inline-block; width:14px; height:14px; border-radius:50%; background-color:#dc3545; box-shadow:0 0 8px rgba(220,53,69,0.6);"></span>
					<strong style="color:#bd2130; font-size:16px;">غير متصل - يلزم ربط الحساب 🔴</strong>
				</div>
			`;
		}

		const html = `
			<div style="border: 2px solid ${borderColor}; background-color: ${bgColor}; border-radius: 10px; padding: 18px 22px; margin-bottom: 15px; box-shadow: 0 2px 6px rgba(0,0,0,0.04);">
				<div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:12px;">
					<div>
						${statusBadge}
						<div style="margin-top: 8px; color: #495057; font-size: 13px;">
							<strong>الرقم المسجل:</strong> <span dir="ltr" style="font-family:monospace; font-size:14px;">${phone}</span> &nbsp;|&nbsp;
							<strong>آخر مزامنة:</strong> ${syncTime}
						</div>
					</div>
					<div style="display:flex; gap:8px; flex-wrap:wrap;">
						<button type="button" class="btn btn-sm btn-primary" onclick="cur_frm.trigger('open_pairing_dialog')">
							<i class="fa fa-key"></i> طلب كود الربط (Pairing Code)
						</button>
						<button type="button" class="btn btn-sm btn-default" onclick="cur_frm.trigger('open_qr_modal')">
							<i class="fa fa-qrcode"></i> مسح QR Code
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

		frm.add_custom_button(__('طلب كود الربط'), function() {
			frm.trigger('open_pairing_dialog');
		}, __('عمليات الربط'));

		frm.add_custom_button(__('مسح QR Code'), function() {
			frm.trigger('open_qr_modal');
		}, __('عمليات الربط'));

		frm.add_custom_button(__('جلب مجموعات واتساب'), function() {
			frm.trigger('fetch_groups_action');
		}, __('المجموعات'));

		frm.add_custom_button(__('إرسال رسالة تجريبية'), function() {
			frm.trigger('open_test_message_dialog');
		}, __('اختبار'));

		frm.add_custom_button(__('تحديث الحالة'), function() {
			frm.trigger('check_status');
		});

		// Secondary menu items
		frm.page.add_menu_item(__('إعادة تشغيل الجلسة'), function() {
			frappe.confirm(__('هل تريد إعادة تشغيل مقبس الواتساب؟'), function() {
				frappe.call({
					method: 'restart_service',
					doc: frm.doc,
					freeze: true,
					freeze_message: __('جاري إعادة التشغيل...'),
					callback: function(r) {
						frappe.show_alert({ message: __('تم إرسال أمر إعادة التشغيل'), indicator: 'green' });
						frm.trigger('check_status');
					}
				});
			});
		});

		frm.page.add_menu_item(__('تسجيل خروج ومسح الجلسة'), function() {
			frappe.confirm(__('تحذير: سيتم إلغاء ربط الحساب ومسح مفاتيح الجلسة. هل أنت متأكد؟'), function() {
				frappe.call({
					method: 'logout_service',
					doc: frm.doc,
					freeze: true,
					freeze_message: __('جاري تسجيل الخروج ومسح الجلسة...'),
					callback: function(r) {
						frappe.msgprint(__('تم تسجيل الخروج بنجاح. يمكنك الآن ربط حساب جديد.'));
						frm.trigger('check_status');
					}
				});
			});
		});
	},

	check_status: function(frm) {
		frappe.call({
			method: 'refresh_status',
			doc: frm.doc,
			freeze: true,
			freeze_message: __('جاري فحص حالة الاتصال بخادم Baileys...'),
			callback: function(r) {
				frm.reload_doc();
				frappe.show_alert({
					message: __('تم تحديث الحالة: ' + (r.message ? r.message.status : 'جاهز')),
					indicator: r.message && r.message.connected ? 'green' : 'orange'
				});
			}
		});
	},

	open_pairing_dialog: function(frm) {
		const defaultPhone = frm.doc.bot_phone_number || frm.doc.connected_phone || '';

		const d = new frappe.ui.Dialog({
			title: __('طلب كود الربط السريع (Pairing Code) 📱'),
			fields: [
				{
					fieldname: 'phone',
					fieldtype: 'Data',
					label: __('رقم هاتف البوت'),
					reqd: 1,
					default: defaultPhone,
					description: __('أدخل رقم الهاتف الدولي أو المحلي (مثال: 01028632620 أو 0569589664)')
				}
			],
			primary_action_label: __('طلب الكود الآن'),
			primary_action: function(values) {
				d.hide();
				frappe.call({
					method: 'request_pairing',
					doc: frm.doc,
					args: {
						phone: values.phone
					},
					freeze: true,
					freeze_message: __('جاري توليد كود الربط من خوادم واتساب...'),
					callback: function(r) {
						frm.reload_doc();
						if (r.message && r.message.code) {
							const formattedCode = r.message.formatted_code || r.message.code;
							const rawCode = r.message.code;
							const cleanPhone = r.message.phone || values.phone;

							const codeDialog = new frappe.ui.Dialog({
								title: __('كود ربط واتساب جاهز! ✅'),
								fields: [
									{
										fieldtype: 'HTML',
										fieldname: 'code_html',
										options: `
											<div style="text-align: center; padding: 20px 10px;">
												<p style="font-size: 14px; color: #495057;">تم توليد كود الربط للرقم: <strong dir="ltr">+${cleanPhone}</strong></p>
												
												<div style="margin: 20px auto; display: inline-block; background: #f8f9fa; border: 2px dashed #007bff; border-radius: 12px; padding: 15px 30px;">
													<span id="wa-pair-code" style="font-size: 32px; font-weight: bold; letter-spacing: 4px; font-family: monospace; color: #1d2124;">
														${formattedCode}
													</span>
												</div>
												
												<div style="margin-top: 10px;">
													<button class="btn btn-sm btn-primary" onclick="navigator.clipboard.writeText('${rawCode}'); frappe.show_alert({message: 'تم نسخ الكود بنجاح!', indicator: 'green'});">
														<i class="fa fa-copy"></i> نسخ الكود
													</button>
												</div>

												<div style="text-align: right; margin-top: 25px; background: #e8f4fd; padding: 15px 20px; border-radius: 8px; font-size: 13px; line-height: 1.8; color: #0c5460;">
													<strong>خطوات التفعيل على هاتفك:</strong>
													<ol style="margin-bottom: 0; padding-right: 20px;">
														<li>افتح تطبيق واتساب على هاتفك.</li>
														<li>توجه إلى: <strong>الإعدادات > الأجهزة المرتبطة > ربط جهاز</strong>.</li>
														<li>اضغط على خيار <strong>"الربط باستخدام رقم الهاتف بدلاً من ذلك"</strong>.</li>
														<li>أدخل الكود الموضح أعلاه (8 خانات) لتأكيد الربط فوراً.</li>
													</ol>
												</div>
											</div>
										`
									}
								],
								primary_action_label: __('تم الإدخال (فحص الاتصال)'),
								primary_action: function() {
									codeDialog.hide();
									setTimeout(() => {
										frm.trigger('check_status');
									}, 3000);
								}
							});
							codeDialog.show();
						} else if (r.message && r.message.status === 'already_connected') {
							frappe.msgprint(__('الواتساب متصل بالفعل بالرقم: ' + r.message.bot_phone));
						} else {
							frappe.msgprint(__('تعذر استلام الكود. يرجى مراجعة سجلات الخادم.'));
						}
					}
				});
			}
		});

		d.show();
	},

	open_qr_modal: function(frm) {
		frappe.call({
			method: 'get_qr',
			doc: frm.doc,
			freeze: true,
			freeze_message: __('جاري جلب رمز الاستجابة السريعة QR...'),
			callback: function(r) {
				if (r.message && r.message.qr_data_url) {
					const qrDialog = new frappe.ui.Dialog({
						title: __('مسح رمز QR لربط واتساب 📷'),
						fields: [
							{
								fieldtype: 'HTML',
								fieldname: 'qr_html',
								options: `
									<div style="text-align:center; padding:15px;">
										<img src="${r.message.qr_data_url}" alt="WhatsApp QR Code" style="max-width:260px; border-radius:8px; box-shadow:0 2px 10px rgba(0,0,0,0.15); margin-bottom:15px;" />
										<p style="font-size:13px; color:#6c757d;">افتح واتساب > الأجهزة المرتبطة > امسح هذا الرمز</p>
									</div>
								`
							}
						],
						primary_action_label: __('تحديث الرمز'),
						primary_action: function() {
							qrDialog.hide();
							frm.trigger('open_qr_modal');
						}
					});
					qrDialog.show();
				} else if (r.message && r.message.status === 'already_connected') {
					frappe.msgprint(__('الواتساب متصل بالفعل بالرقم: ' + r.message.bot_phone));
				} else {
					frappe.msgprint(__('رمز QR غير متاح حالياً. يرجى الانتظار ثوانٍ أو استخدام كود الربط (Pairing Code).'));
				}
			}
		});
	},

	fetch_groups_action: function(frm) {
		frappe.call({
			method: 'sync_groups',
			doc: frm.doc,
			freeze: true,
			freeze_message: __('جاري استعلام مجموعات واتساب من Baileys...'),
			callback: function(r) {
				frm.reload_doc();
				if (r.message && r.message.status === 'ok') {
					frappe.msgprint({
						title: __('تم جلب المجموعات بنجاح ✅'),
						indicator: 'green',
						message: __('تم تحديث جدول مجموعات المشاريع بإجمالي ' + (r.message.count || 0) + ' مجموعة.')
					});
				}
			}
		});
	},

	open_test_message_dialog: function(frm) {
		const d = new frappe.ui.Dialog({
			title: __('إرسال رسالة تجريبية 💬'),
			fields: [
				{
					fieldname: 'recipient',
					fieldtype: 'Data',
					label: __('رقم المستلم أو JID المجموعة'),
					reqd: 1,
					description: __('مثال: 01028632620 أو معرف المجموعة 120363...@g.us')
				},
				{
					fieldname: 'message',
					fieldtype: 'Small Text',
					label: __('نص الرسالة'),
					reqd: 1,
					default: 'مرحباً، هذه رسالة اختبار من نظام Elsaidy ERP عبر Elsaidy WhatsApp Hub 🚀'
				}
			],
			primary_action_label: __('إرسال الآن'),
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
							frappe.show_alert({ message: __('تم إرسال الرسالة بنجاح!'), indicator: 'green' });
						} else {
							frappe.msgprint(__('فشل الإرسال: ' + (r.message ? r.message.error : 'خطأ غير معروف')));
						}
					}
				});
			}
		});
		d.show();
	}
});
