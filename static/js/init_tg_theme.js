document.addEventListener('DOMContentLoaded', function() {
    const body = document.body;

    function initTelegramTheme() {
        if (window.Telegram && window.Telegram.WebApp) {
            const tgWebApp = window.Telegram.WebApp;
            
            if (tgWebApp.colorScheme === 'dark') {
                body.classList.add('dark-theme');
            } else {
                body.classList.remove('dark-theme');
            }
            
            tgWebApp.onEvent('themeChanged', function() {
                if (tgWebApp.colorScheme === 'dark') {
                    body.classList.add('dark-theme');
                } else {
                    body.classList.remove('dark-theme');
                }
            });
            
            tgWebApp.expand();
        } else {
            const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
            if (prefersDark) {
                body.classList.add('dark-theme');
            } else {
                body.classList.remove('dark-theme');
            }
        }
    }

    initTelegramTheme();
});