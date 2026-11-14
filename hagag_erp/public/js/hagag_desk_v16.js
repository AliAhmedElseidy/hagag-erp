/* === Elsaidy ERP Desk Enhancements v16 === */
(function() {
    'use strict';

    // Scoped navbar cleanup (only runs when navbar user dropdown opens)
    function cleanNavbarUserMenu() {
        var menu = document.querySelector('.dropdown-navbar-user');
        if (!menu) return;
        var items = menu.querySelectorAll('li, a');
        items.forEach(function(el) {
            var txt = (el.textContent || '').trim();
            if (txt.includes('معلومات عن النظام') || txt.includes('دعم فرابيه') ||
                txt.includes('About') || (txt.includes('Support') && !txt.includes('Elsaidy'))) {
                el.style.setProperty('display', 'none', 'important');
            }
        });
    }

    // Run only on dropdown click rather than polling the whole DOM
    document.addEventListener('click', function(e) {
        if (e.target && e.target.closest && e.target.closest('.dropdown-navbar-user, .nav-item.dropdown-user')) {
            setTimeout(cleanNavbarUserMenu, 20);
        }
    });

    // Clean Document Title
    function updateTitle() {
        if (!document.title) return;
        var t = document.title;
        var brandings = [
            ["Frappe Framework", "Elsaidy Core"],
            ["Frappe HR", "Elsaidy HR"],
            ["ERPNext", "Elsaidy ERP"],
            ["Hagag ERP", "Elsaidy ERP"],
            ["Hagag", "Elsaidy"],
            ["حجاج", "الصعيدي"]
        ];
        brandings.forEach(function(pair) {
            if (t.includes(pair[0])) {
                t = t.split(pair[0]).join(pair[1]);
            }
        });
        if (t !== document.title) {
            document.title = t;
        }
    }

    // Fix Desktop App Launcher Icons & Labels
    function fixDesktopAppLauncher() {
        var icons = document.querySelectorAll('.desktop-icon');
        if (!icons || !icons.length) return;

        var isRTL = document.documentElement.dir === 'rtl' || (window.frappe && frappe.boot && frappe.boot.lang === 'ar');

        icons.forEach(function(icon) {
            var link = icon.querySelector('a.icon-link');
            var href = link ? link.getAttribute('href') : '';
            var caption = icon.querySelector('.icon-caption');
            if (!caption) return;

            var titleLink = caption.querySelector('.icon-title');

            // 1. Helpdesk Missing Caption Fix
            if (href && href.includes('/helpdesk')) {
                var helpdeskLabel = isRTL ? 'خدمة العملاء والدعم' : 'Elsaidy Support';
                if (!titleLink) {
                    var a = document.createElement('a');
                    a.className = 'icon-title';
                    a.href = href;
                    a.setAttribute('data-toggle', 'tooltip');
                    a.setAttribute('data-original-title', helpdeskLabel);
                    a.textContent = helpdeskLabel;
                    caption.appendChild(a);
                } else if (!titleLink.textContent.trim()) {
                    titleLink.textContent = helpdeskLabel;
                    titleLink.setAttribute('data-original-title', helpdeskLabel);
                }
            }

            // 2. CRM Label Polish
            if (href && (href.includes('/crm') || href.includes('/fcrm'))) {
                var crmLabel = isRTL ? 'إدارة علاقات العملاء' : 'Elsaidy CRM';
                if (titleLink && (titleLink.textContent.trim() === 'CRM' || !titleLink.textContent.trim())) {
                    titleLink.textContent = crmLabel;
                    titleLink.setAttribute('data-original-title', crmLabel);
                }
            }
        });
    }

    if (window.frappe && frappe.router) {
        frappe.router.on('change', function() {
            updateTitle();
            setTimeout(fixDesktopAppLauncher, 100);
            setTimeout(fixDesktopAppLauncher, 500);
        });
    }
    window.addEventListener('DOMContentLoaded', function() {
        updateTitle();
        setTimeout(fixDesktopAppLauncher, 100);
        setTimeout(fixDesktopAppLauncher, 500);
    });

    if (window.$ && $(document).on) {
        $(document).on('desktop_screen', function() {
            setTimeout(fixDesktopAppLauncher, 50);
            setTimeout(fixDesktopAppLauncher, 300);
        });
    }
})();
