/* OCTO CRM APM frontend helpers */

function getSessionId() {
    const existing = localStorage.getItem('octo-session-id');
    if (existing) return existing;
    const created = crypto.randomUUID();
    localStorage.setItem('octo-session-id', created);
    return created;
}

async function checkSession() {
    try {
        const resp = await fetch('/api/auth/session');
        const data = await resp.json();
        const userInfo = document.getElementById('user-info');
        if (data.authenticated && userInfo) {
            userInfo.textContent = `${data.username} (${data.role})`;
            const loginBtn = document.querySelector('.btn-login');
            if (loginBtn) {
                loginBtn.textContent = 'Logout';
                loginBtn.href = '#';
                loginBtn.onclick = async (event) => {
                    event.preventDefault();
                    await fetch('/api/auth/logout', {method: 'POST'});
                    window.location.href = '/login';
                };
            }
        }
    } catch (error) {
        console.error('Session check failed:', error);
    }
}

async function trackPageView() {
    try {
        const navEntry = performance.getEntriesByType('navigation')[0];
        const loadTime = navEntry ? Math.round(navEntry.duration) : Math.round(performance.now());
        await fetch('/api/analytics/track', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                page: window.location.pathname,
                visitor_region: Intl.DateTimeFormat().resolvedOptions().timeZone || '',
                load_time_ms: loadTime,
                referrer: document.referrer || '',
                session_id: getSessionId(),
            }),
        });
    } catch (error) {
        console.error('Page tracking failed:', error);
    }
}

window.addEventListener('load', () => {
    checkSession();
    trackPageView();
});
