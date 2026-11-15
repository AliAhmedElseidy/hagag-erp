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

    // 3. Desktop App Launcher Layout & Label Polishing
    function fixDesktopLauncher() {
        // Inject override CSS once
        if (!document.getElementById('elsaidy-desktop-override-style')) {
            var st = document.createElement('style');
            st.id = 'elsaidy-desktop-override-style';
            st.textContent = `
                body.desktop-page .desktop-container > .icons-container > .icons {
                    grid-template-columns: repeat(auto-fill, minmax(130px, 1fr)) !important;
                    max-width: 960px !important;
                    margin: 0 auto !important;
                    gap: 16px !important;
                }
                body.desktop-page .desktop-icon,
                .desktop-icon {
                    width: 135px !important;
                    min-width: 125px !important;
                    height: auto !important;
                    min-height: 115px !important;
                }
                body.desktop-page .desktop-icon .icon-caption,
                .desktop-icon .icon-caption {
                    width: 100% !important;
                    max-width: 100% !important;
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

            // 1. Helpdesk / Support Missing Label
            if (href.indexOf('helpdesk') !== -1 || html.indexOf('helpdesk') !== -1) {
                var hdLabel = isRTL ? 'خدمة العملاء والدعم' : 'Elsaidy Support';
                var titleLink = caption.querySelector('.icon-title');
                if (!titleLink) {
                    caption.innerHTML = '<a class="icon-title" href="/helpdesk" data-toggle="tooltip" data-original-title="' + hdLabel + '">' + hdLabel + '</a>';
                } else if (!titleLink.textContent.trim()) {
                    titleLink.textContent = hdLabel;
                }
            }

            // 2. Builder Label (concise to prevent any overflow)
            if (href.indexOf('builder') !== -1) {
                var bLink = caption.querySelector('.icon-title');
                if (bLink) {
                    bLink.textContent = isRTL ? 'بناء وتصميم المواقع' : 'Builder';
                }
            }

            // 3. Insights Label (concise to prevent any overflow)
            if (href.indexOf('insights') !== -1) {
                var iLink = caption.querySelector('.icon-title');
                if (iLink) {
                    iLink.textContent = isRTL ? 'تحليلات الأعمال (BI)' : 'Insights';
                }
            }
        });
    }

    // Debounced safe DOM sweep
    var sweepTimeout = null;
    function scheduleSweep() {
        if (sweepTimeout) clearTimeout(sweepTimeout);
        sweepTimeout = setTimeout(function () {
            dismissOnboarding();
            purgeOnboardingDOM();
            sanitizeDocumentTitle();
            fixDesktopLauncher();
        }, 100);
    }

    // Listen to route changes rather than continuous characterData mutations
    if (window.frappe && frappe.router) {
        frappe.router.on('change', scheduleSweep);
    }
    window.addEventListener('DOMContentLoaded', scheduleSweep);

    if (window.$ && $(document).on) {
        $(document).on('desktop_screen', function () {
            fixDesktopLauncher();
            setTimeout(fixDesktopLauncher, 100);
            setTimeout(fixDesktopLauncher, 300);
        });
    }

    // Throttled observer strictly for modal/body popups (childList only, no characterData)
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
                    if (node.classList && (
                        node.classList.contains('desktop-icon') ||
                        node.classList.contains('icons-container') ||
                        node.classList.contains('desktop-wrapper')
                    )) {
                        fixDesktopLauncher();
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
