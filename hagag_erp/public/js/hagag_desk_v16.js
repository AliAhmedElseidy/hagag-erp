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

    // Dynamic Style Injection for Absolute Layout Guarantee
    function injectOverrideStyles() {
        if (document.getElementById('elsaidy-desktop-override-style')) return;
        var style = document.createElement('style');
        style.id = 'elsaidy-desktop-override-style';
        style.textContent = `
            body.desktop-page .desktop-container > .icons-container > .icons {
                grid-template-columns: repeat(auto-fill, minmax(130px, 1fr)) !important;
                max-width: 960px !important;
                margin: 0 auto !important;
                gap: 16px !important;
                row-gap: 20px !important;
                justify-items: center !important;
            }
            body.desktop-page .desktop-icon,
            .desktop-wrapper .desktop-icon,
            .desktop-icon {
                width: 135px !important;
                min-width: 125px !important;
                height: auto !important;
                min-height: 115px !important;
                padding: 8px 4px !important;
                margin: 4px !important;
            }
            body.desktop-page .desktop-icon .icon-caption,
            .desktop-icon .icon-caption {
                width: 100% !important;
                max-width: 100% !important;
                height: auto !important;
                min-height: 34px !important;
                white-space: normal !important;
                text-wrap: wrap !important;
                display: flex !important;
                flex-direction: column !important;
                align-items: center !important;
                justify-content: center !important;
                text-align: center !important;
            }
            body.desktop-page .desktop-icon .icon-title,
            body.desktop-page a.icon-title,
            .desktop-icon .icon-title {
                width: 100% !important;
                white-space: normal !important;
                word-break: break-word !important;
                overflow-wrap: break-word !important;
                line-height: 1.25 !important;
                font-size: 13px !important;
                font-weight: 500 !important;
                max-height: 2.8em !important;
                overflow: hidden !important;
                text-overflow: unset !important;
                display: -webkit-box !important;
                -webkit-line-clamp: 2 !important;
                -webkit-box-orient: vertical !important;
                text-align: center !important;
            }
            .widget.number-widget-box .widget-head,
            .number-widget-box .widget-head {
                height: auto !important;
                min-height: 38px !important;
                align-items: flex-start !important;
            }
            .widget.number-widget-box .widget-title,
            .number-widget-box .widget-title,
            .widget.number-widget-box .widget-title .ellipsis,
            .number-widget-box .widget-title .ellipsis,
            .widget.number-widget-box .ellipsis {
                width: 100% !important;
                white-space: normal !important;
                word-break: break-word !important;
                overflow-wrap: break-word !important;
                line-height: 1.25 !important;
                max-height: 2.8em !important;
                overflow: hidden !important;
                text-overflow: unset !important;
                display: -webkit-box !important;
                -webkit-line-clamp: 2 !important;
                -webkit-box-orient: vertical !important;
                height: auto !important;
            }
        `;
        document.head.appendChild(style);
    }

    // Fix Desktop App Launcher Icons & Labels
    function fixDesktopAppLauncher() {
        injectOverrideStyles();

        var icons = document.querySelectorAll('.desktop-icon');
        if (!icons || !icons.length) return;

        var isRTL = document.documentElement.dir === 'rtl' || (window.frappe && frappe.boot && frappe.boot.lang === 'ar');

        icons.forEach(function(icon) {
            var link = icon.querySelector('a.icon-link');
            var href = link ? (link.getAttribute('href') || '') : '';
            var caption = icon.querySelector('.icon-caption');
            if (!caption) return;

            // 1. Helpdesk Missing Caption Fix
            if (href.indexOf('helpdesk') !== -1 || (icon.innerHTML && icon.innerHTML.indexOf('helpdesk') !== -1)) {
                var helpdeskLabel = isRTL ? 'خدمة العملاء' : 'Elsaidy Support';
                var titleLink = caption.querySelector('.icon-title');
                if (!titleLink) {
                    caption.innerHTML = '<a class="icon-title" href="' + (href || '/helpdesk') + '" data-toggle="tooltip" data-original-title="' + helpdeskLabel + '">' + helpdeskLabel + '</a>';
                } else if (!titleLink.textContent.trim()) {
                    titleLink.textContent = helpdeskLabel;
                    titleLink.setAttribute('data-original-title', helpdeskLabel);
                }
            }

            // 2. Concise Clean Titles to Eliminate Any Truncation
            var tLink = caption.querySelector('.icon-title');
            if (tLink) {
                var curText = tLink.textContent.trim();
                var cleanMap = {
                    'إدارة الأعمال (ERP)': 'إدارة الأعمال',
                    'الموارد البشرية (HR)': 'الموارد البشرية',
                    'إدارة علاقات العملاء (CRM)': 'علاقات العملاء',
                    'إدارة علاقات العملاء': 'علاقات العملاء',
                    'خدمة العملاء والدعم': 'خدمة العملاء',
                    'قاعدة المعرفة والتوثيق': 'قاعدة المعرفة',
                    'المساعد الذكي (AI)': 'المساعد الذكي',
                    'النظام الأساسي (Core)': 'النظام الأساسي',
                    'بناء وتصميم المواقع': 'بناء المواقع',
                    'تحليلات الأعمال (BI)': 'تحليلات الأعمال'
                };
                if (cleanMap[curText]) {
                    tLink.textContent = cleanMap[curText];
                    tLink.setAttribute('data-original-title', cleanMap[curText]);
                }
            }
        });
    }

    if (window.frappe && frappe.router) {
        frappe.router.on('change', function() {
            updateTitle();
            fixDesktopAppLauncher();
            setTimeout(fixDesktopAppLauncher, 100);
            setTimeout(fixDesktopAppLauncher, 400);
            setTimeout(fixDesktopAppLauncher, 1000);
        });
    }
    window.addEventListener('DOMContentLoaded', function() {
        updateTitle();
        fixDesktopAppLauncher();
        setTimeout(fixDesktopAppLauncher, 100);
        setTimeout(fixDesktopAppLauncher, 400);
        setTimeout(fixDesktopAppLauncher, 1000);
    });

    if (window.$ && $(document).on) {
        $(document).on('desktop_screen', function() {
            fixDesktopAppLauncher();
            setTimeout(fixDesktopAppLauncher, 100);
            setTimeout(fixDesktopAppLauncher, 400);
            setTimeout(fixDesktopAppLauncher, 1000);
        });
    }

    // Continuous polling check while on /desk
    setInterval(function() {
        if (document.querySelector('.desktop-icon')) {
            fixDesktopAppLauncher();
        }
    }, 400);
})();
