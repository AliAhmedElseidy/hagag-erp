/**
 * Elsaidy ERP - Universal Enterprise White-Labeling & Auto-Dismiss Engine
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
            keys.forEach(k => {
                localStorage.setItem(k, '1');
                sessionStorage.setItem(k, '1');
            });
            // Specific flags for Helpdesk and CRM Vue 3 state
            localStorage.setItem('helpdesk:onboarding:dismissed', 'true');
            localStorage.setItem('crm:onboarding:dismissed', 'true');
            localStorage.setItem('fcrm:setup_completed', 'true');
        } catch (e) {}
    }

    dismissOnboarding();

    // 2. Replacements Dictionary (Strict Hierarchy)
    const REPLACEMENTS = [
        [/\bFrappe Helpdesk\b/gi, 'Elsaidy Support'],
        [/\bHelpdesk\b/gi, 'Elsaidy Support'],
        [/\bFrappe CRM\b/gi, 'Elsaidy CRM'],
        [/\bHagag CRM\b/gi, 'Elsaidy CRM'],
        [/\bFrappe Insights\b/gi, 'Elsaidy BI & Insights'],
        [/\bInsights\b/gi, 'Elsaidy BI & Insights'],
        [/\bFrappe HR\b/gi, 'Elsaidy HR'],
        [/\bHagag HR\b/gi, 'Elsaidy HR'],
        [/\bFrappe Builder\b/gi, 'Elsaidy Builder'],
        [/\bFrappe Wiki\b/gi, 'Elsaidy Wiki'],
        [/\bFrappe Framework\b/gi, 'Elsaidy Core | النظام الأساسي'],
        [/إطار العمل/g, 'Elsaidy Core | النظام الأساسي'],
        [/شركة حجاج/g, 'شركة ركن سبل الأفق للمقاولات'],
        [/من حجاج للمقاولات/g, 'شركة ركن سبل الأفق للمقاولات'],
        [/مساعد حجاج الذكي/g, 'مساعد Elsaidy الذكي'],
        [/حجاج/g, 'الصعيدي'],
        [/\bHagag\b/gi, 'Elsaidy'],
        [/\bERPNext\b/gi, 'Elsaidy ERP'],
        [/\bErp Elsaidy\b/gi, 'Elsaidy ERP'],
        [/\bFrappe\b/gi, 'Elsaidy']
    ];

    function sanitizeText(str) {
        if (!str || typeof str !== 'string') return str;
        let res = str;
        for (let i = 0; i < REPLACEMENTS.length; i++) {
            res = res.replace(REPLACEMENTS[i][0], REPLACEMENTS[i][1]);
        }
        return res;
    }

    function sanitizeNode(node) {
        if (!node) return;
        if (node.nodeType === Node.TEXT_NODE) {
            const val = node.nodeValue;
            if (val && (
                val.includes('Frappe') || val.includes('Hagag') || val.includes('حجاج') ||
                val.includes('ERPNext') || val.includes('إطار العمل')
            )) {
                node.nodeValue = sanitizeText(val);
            }
        } else if (node.nodeType === Node.ELEMENT_NODE) {
            // Avoid touching code, script or style tags
            const tag = node.tagName.toLowerCase();
            if (tag === 'script' || tag === 'style' || tag === 'textarea' || tag === 'input') return;

            // Check title attributes
            if (node.hasAttribute('title')) {
                const title = node.getAttribute('title');
                if (title && (title.includes('Frappe') || title.includes('Hagag') || title.includes('حجاج'))) {
                    node.setAttribute('title', sanitizeText(title));
                }
            }

            // Remove onboarding containers if they appear
            if (node.classList && (
                node.classList.contains('driver-popover') ||
                node.classList.contains('onboarding-widget') ||
                node.classList.contains('tour-popup')
            )) {
                node.style.display = 'none';
            }

            for (let child = node.firstChild; child; child = child.nextSibling) {
                sanitizeNode(child);
            }
        }
    }

    function sanitizeDocumentTitle() {
        if (document.title && (
            document.title.includes('Frappe') || document.title.includes('Hagag') ||
            document.title.includes('حجاج') || document.title.includes('ERPNext')
        )) {
            document.title = sanitizeText(document.title);
        }
    }

    // Run on ready and listen for DOM mutations
    function init() {
        sanitizeDocumentTitle();
        if (document.body) {
            sanitizeNode(document.body);
        }

        const observer = new MutationObserver(function (mutations) {
            dismissOnboarding();
            sanitizeDocumentTitle();
            for (let i = 0; i < mutations.length; i++) {
                const m = mutations[i];
                if (m.type === 'childList') {
                    for (let j = 0; j < m.addedNodes.length; j++) {
                        sanitizeNode(m.addedNodes[j]);
                    }
                } else if (m.type === 'characterData') {
                    sanitizeNode(m.target);
                }
            }
        });

        observer.observe(document.documentElement, {
            childList: true,
            subtree: true,
            characterData: true
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
