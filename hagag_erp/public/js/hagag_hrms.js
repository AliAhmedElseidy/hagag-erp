/* HAGAG HR - Branding */

(function () {
    "use strict";

    const HAGAG_TITLE = "Hagag HR";

    function applyHagagBranding() {
        document.title = HAGAG_TITLE;

                
        const walker = document.createTreeWalker(
            document.body,
            NodeFilter.SHOW_TEXT
        );

        const nodes = [];
        let node;

        while ((node = walker.nextNode())) {
            nodes.push(node);
        }

        nodes.forEach(function (textNode) {
            if (!textNode.nodeValue) return;

            const replaced = textNode.nodeValue
                .replace(/Frappe HR/g, "Hagag HR")
                .replace(/FrappeHR/g, "Hagag HR");

            if (replaced !== textNode.nodeValue) {
                textNode.nodeValue = replaced;
            }
        });
    }

    function start() {
        applyHagagBranding();

        const observer = new MutationObserver(function () {
            applyHagagBranding();
        });

        observer.observe(document.body, {
            childList: true,
            subtree: true
        });
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", start);
    } else {
        start();
    }
})();
