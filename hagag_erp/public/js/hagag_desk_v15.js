/* === Hagag UIUX Desk JS v15 === */
$(document).ready(function() { setInterval(function() { $('.dropdown-item').filter(function() { var t = $(this).text(); return t.includes('معلومات عن النظام') || t.includes('دعم فرابيه') || t.includes('About') || t.includes('Support'); }).hide(); }, 500); });
