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

    // Debounced safe DOM sweep
    var sweepTimeout = null;
    function scheduleSweep() {
        if (sweepTimeout) clearTimeout(sweepTimeout);
        sweepTimeout = setTimeout(function () {
            dismissOnboarding();
            purgeOnboardingDOM();
            sanitizeDocumentTitle();
        }, 150);
    }

    // Listen to route changes rather than continuous characterData mutations
    if (window.frappe && frappe.router) {
        frappe.router.on('change', scheduleSweep);
    }
    window.addEventListener('DOMContentLoaded', scheduleSweep);

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
