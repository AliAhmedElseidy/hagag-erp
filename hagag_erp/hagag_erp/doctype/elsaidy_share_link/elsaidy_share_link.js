// Copyright (c) 2026, Elsaidy ERP and contributors
// For license information, please see license.txt

frappe.ui.form.on("Elsaidy Share Link", {
    refresh: function(frm) {
        if (!frm.is_new()) {
            // Copy Link button
            frm.add_custom_button(__("نسخ رابط المشاهدة"), function() {
                const fullUrl = window.location.origin + frm.doc.share_url;
                navigator.clipboard.writeText(fullUrl).then(() => {
                    frappe.show_alert({message: __("تم نسخ رابط المشاهدة إلى الحافظة"), indicator: "green"});
                });
            });

            // Revoke button if not already revoked
            if (!frm.doc.is_revoked) {
                frm.add_custom_button(__("إلغاء الرابط فوراً"), function() {
                    frappe.confirm(__("هل أنت متأكد من رغبتك في إلغاء هذا الرابط فوراً؟ لن يتمكن أي شخص من استخدامه بعد الآن."), function() {
                        frm.call("revoke").then(r => {
                            frm.reload_doc();
                        });
                    });
                }).addClass("btn-danger");
            }
        }
    }
});
