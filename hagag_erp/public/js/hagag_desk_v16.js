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
