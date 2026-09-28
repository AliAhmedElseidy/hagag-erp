/* === Hagag UIUX Desk JS v16 (The Sniper) === */
(function() {
    function cleanMenu() {
        document.querySelectorAll('.dropdown-item, .dropdown-menu li, a, button').forEach(function(el) {
            var txt = el.textContent || '';
            if (txt.includes('معلومات عن النظام') || txt.includes('دعم فرابيه') || txt.includes('About') || txt.includes('Support')) {
                el.style.setProperty('display', 'none', 'important');
                if(el.parentElement && el.parentElement.tagName === 'LI') {
                    el.parentElement.style.setProperty('display', 'none', 'important');
                }
            }
        });
    }
    document.addEventListener('click', function() { setTimeout(cleanMenu, 10); setTimeout(cleanMenu, 50); setTimeout(cleanMenu, 100); });
    var observer = new MutationObserver(cleanMenu);
    if (document.body) { observer.observe(document.body, { childList: true, subtree: true }); }
    else { document.addEventListener('DOMContentLoaded', function() { observer.observe(document.body, { childList: true, subtree: true }); }); }
})();

/* === Hagag Dynamic Branding === */
(function() {
    "use strict";

    var branding = [
        ["Frappe Framework", "Hagag Admin"],
        ["Frappe HR", "Hagag HR"],
        ["ERPNext", "Hagag ERP"],
        ["Frappe", "Hagag"]
    ];

    function replaceText(node) {
        if (!node || node.nodeType !== Node.TEXT_NODE) return;

        var value = node.nodeValue;
        var changed = value;

        branding.forEach(function(item) {
            changed = changed.split(item[0]).join(item[1]);
        });

        if (changed !== value) {
            node.nodeValue = changed;
        }
    }

    function scan(root) {
        if (!root) return;

        if (root.nodeType === Node.TEXT_NODE) {
            replaceText(root);
            return;
        }

        var walker = document.createTreeWalker(
            root,
            NodeFilter.SHOW_TEXT,
            null
        );

        var node;
        while ((node = walker.nextNode())) {
            replaceText(node);
        }
    }

    function updateTitle() {
        if (document.title) {
            branding.forEach(function(item) {
                document.title = document.title.split(item[0]).join(item[1]);
            });
        }
    }

    function initBranding() {
        scan(document.body);
        updateTitle();

        var observer = new MutationObserver(function(mutations) {
            mutations.forEach(function(mutation) {
                mutation.addedNodes.forEach(function(node) {
                    scan(node);
                });
            });

            updateTitle();
        });

        observer.observe(document.body, {
            childList: true,
            subtree: true
        });
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", initBranding, { once: true });
    } else {
        initBranding();
    }
})();
