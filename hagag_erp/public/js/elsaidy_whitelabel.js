/**
 * Elsaidy ERP - Enterprise White-Labeling & Auto-Dismiss Engine
 * شركة ركن سبل الأفق للمقاولات
 */
(function () {
    'use strict';

    // 1. Auto-Dismiss Onboarding States in Browser Storage
    function dismissOnboarding() {
        try {
            const keys = [
                'fcrm_onboarding',
                'crm_onboarding_completed',
                'hd_onboarding',
                'helpdesk_onboarding_completed',
                'welcome_tour',
                'frappe_onboarding_status',
                'initial_setup_skipped',
                'persona_captured',
                'onboarding_last_step',
                'desk_onboarding_completed'
            ];
            keys.forEach(function (k) {
                localStorage.setItem(k, '1');
                sessionStorage.setItem(k, '1');
            });
            localStorage.setItem('helpdesk:onboarding:dismissed', 'true');
            localStorage.setItem('crm:onboarding:dismissed', 'true');
            localStorage.setItem('fcrm:setup_completed', 'true');
        } catch (e) {}
    }

    dismissOnboarding();

    // 2. Concise Brand Replacements
    const REPLACEMENTS = [
        [/\bFrappe Helpdesk\b/g, 'Elsaidy Support'],
        [/\bFrappe CRM\b/g, 'Elsaidy CRM'],
        [/\bHagag CRM\b/g, 'Elsaidy CRM'],
        [/\bFrappe Insights\b/g, 'Elsaidy Insights'],
        [/\bFrappe HR\b/g, 'Elsaidy HR'],
        [/\bHagag HR\b/g, 'Elsaidy HR'],
        [/\bFrappe Builder\b/g, 'Elsaidy Builder'],
        [/\bFrappe Wiki\b/g, 'Elsaidy Wiki'],
        [/\bFrappe Framework\b/g, 'Elsaidy Core'],
        [/إطار العمل/g, 'النظام الأساسي'],
        [/شركة حجاج/g, 'شركة ركن سبل الأفق للمقاولات'],
        [/من حجاج للمقاولات/g, 'شركة ركن سبل الأفق للمقاولات'],
        [/مساعد حجاج الذكي/g, 'مساعد Elsaidy الذكي'],
        [/حجاج/g, 'الصعيدي'],
        [/\bHagag\b/g, 'Elsaidy'],
        [/\bERPNext\b/g, 'Elsaidy ERP']
    ];

    function sanitizeText(str) {
        if (!str || typeof str !== 'string') return str;
        var res = str;
        for (var i = 0; i < REPLACEMENTS.length; i++) {
            res = res.replace(REPLACEMENTS[i][0], REPLACEMENTS[i][1]);
        }
        return res;
    }

    function sanitizeDocumentTitle() {
        if (document.title && (
            document.title.includes('Frappe') || document.title.includes('Hagag') ||
            document.title.includes('حجاج') || document.title.includes('ERPNext')
        )) {
            document.title = sanitizeText(document.title);
        }
    }

    // Dismiss any active driver/tour popovers immediately
    function purgeOnboardingDOM() {
        var popovers = document.querySelectorAll(
            '.driver-popover, .driver-overlay, .shepherd-element, .shepherd-modal-overlay-container, .onboarding-widget'
        );
        popovers.forEach(function (el) {
            el.style.setProperty('display', 'none', 'important');
        });
    }

    // Dismiss unwanted support & about links from user dropdown
    function purgeUnwantedUserMenuItems() {
        var items = document.querySelectorAll('.dropdown-menu a, .dropdown-menu button, .dropdown-menu .dropdown-item, #toolbar-user .dropdown-item, .standard-actions .dropdown-item');
        items.forEach(function (el) {
            var text = (el.textContent || '').trim();
            var href = el.getAttribute('href') || '';
            var onclick = el.getAttribute('onclick') || '';
            if (
                text === 'Frappe Support' ||
                text === 'دعم Frappe' ||
                text === 'About' ||
                text === 'حول' ||
                text === 'Documentation' ||
                text === 'التوثيق' ||
                href.indexOf('frappe.io/support') !== -1 ||
                onclick.indexOf('show_about') !== -1
            ) {
                var parentLi = el.closest('li') || el;
                parentLi.style.setProperty('display', 'none', 'important');
            }
        });
    }

    // 3. Desktop App Launcher Layout & Label Polishing
    function fixDesktopLauncher() {
        // Inject override CSS once into head
        if (!document.getElementById('elsaidy-desktop-override-style')) {
            var st = document.createElement('style');
            st.id = 'elsaidy-desktop-override-style';
            st.textContent = `
                body.desktop-page .desktop-container > .icons-container > .icons {
                    grid-template-columns: repeat(auto-fill, minmax(130px, 1fr)) !important;
                    max-width: 960px !important;
                    margin: 0 auto !important;
                    gap: 16px !important;
                    row-gap: 20px !important;
                }
                body.desktop-page .desktop-icon,
                .desktop-icon {
                    width: 135px !important;
                    min-width: 125px !important;
                    height: auto !important;
                    min-height: 115px !important;
                    padding: 8px 4px !important;
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
                    line-height: 1.25 !important;
                    font-size: 13px !important;
                    font-weight: 500 !important;
                    text-overflow: unset !important;
                    display: -webkit-box !important;
                    -webkit-line-clamp: 2 !important;
                    -webkit-box-orient: vertical !important;
                    text-align: center !important;
                }
            `;
            (document.head || document.documentElement).appendChild(st);
        }

        var icons = document.querySelectorAll('.desktop-icon');
        if (!icons || !icons.length) return;

        var isRTL = document.documentElement.dir === 'rtl' || (window.frappe && frappe.boot && frappe.boot.lang === 'ar');

        icons.forEach(function (icon) {
            var caption = icon.querySelector('.icon-caption');
            if (!caption) return;

            var link = icon.querySelector('a.icon-link') || icon.querySelector('a[href]');
            var href = link ? (link.getAttribute('href') || '') : '';
            var html = icon.innerHTML || '';

            // 1. Helpdesk / Support Missing Label Fix
            if (href.indexOf('helpdesk') !== -1 || html.indexOf('helpdesk') !== -1 || html.indexOf('favicon.svg') !== -1 || html.indexOf('helpdesk/desk') !== -1) {
                var hdLabel = isRTL ? 'خدمة العملاء' : 'Elsaidy Support';
                var titleLink = caption.querySelector('.icon-title');
                if (!titleLink) {
                    caption.innerHTML = '<a class="icon-title" href="/helpdesk" data-toggle="tooltip" data-original-title="' + hdLabel + '">' + hdLabel + '</a>';
                } else if (!titleLink.textContent.trim()) {
                    titleLink.textContent = hdLabel;
                    titleLink.setAttribute('data-original-title', hdLabel);
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

    function monitorDesktop() {
        fixDesktopLauncher();
        var count = 0;
        var t = setInterval(function () {
            count++;
            fixDesktopLauncher();
            if (count > 50) clearInterval(t);
        }, 200);
    }

    // Continuous poll when on desktop screen
    setInterval(function() {
        if (document.querySelector('.desktop-icon')) {
            fixDesktopLauncher();
        }
    }, 500);

    // Debounced safe DOM sweep
    var sweepTimeout = null;
    function scheduleSweep() {
        if (sweepTimeout) clearTimeout(sweepTimeout);
        sweepTimeout = setTimeout(function () {
            dismissOnboarding();
            purgeOnboardingDOM();
            purgeUnwantedUserMenuItems();
            sanitizeDocumentTitle();
            monitorDesktop();
        }, 100);
    }

    // Run on startup and on all navigation events
    monitorDesktop();

    if (window.frappe && frappe.router) {
        frappe.router.on('change', scheduleSweep);
    }
    window.addEventListener('DOMContentLoaded', scheduleSweep);

    if (window.$ && $(document).on) {
        $(document).on('desktop_screen', monitorDesktop);
        $(document).on('shown.bs.dropdown', purgeUnwantedUserMenuItems);
    }
    document.addEventListener('click', function () {
        setTimeout(purgeUnwantedUserMenuItems, 10);
    });

    // Observe body for modals and dynamic desktop container mounting
    var modalObserver = new MutationObserver(function (mutations) {
        for (var i = 0; i < mutations.length; i++) {
            var m = mutations[i];
            if (m.addedNodes && m.addedNodes.length) {
                for (var j = 0; j < m.addedNodes.length; j++) {
                    var node = m.addedNodes[j];
                    if (node.classList && (
                        node.classList.contains('driver-popover') ||
                        node.classList.contains('onboarding-widget') ||
                        node.classList.contains('shepherd-element')
                    )) {
                        node.style.setProperty('display', 'none', 'important');
                    }
                }
            }
        }
    });

    if (document.body) {
        modalObserver.observe(document.body, { childList: true, subtree: false });
    } else {
        document.addEventListener('DOMContentLoaded', function () {
            modalObserver.observe(document.body, { childList: true, subtree: false });
        });
    }
})();
