/* OCTO CRM APM frontend helpers */
/* Restore native fetch — APM RUM agent patches fetch/XHR and can break API calls */
const _fetch = window.__nativeFetch || window.fetch.bind(window);

function _uuid() {
    if (typeof crypto !== 'undefined' && crypto.randomUUID) return crypto.randomUUID();
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
        var r = Math.random() * 16 | 0; return (c === 'x' ? r : (r & 0x3 | 0x8)).toString(16);
    });
}

function getSessionId() {
    const existing = localStorage.getItem('octo-session-id');
    if (existing) return existing;
    const created = _uuid();
    localStorage.setItem('octo-session-id', created);
    return created;
}

async function checkSession() {
    try {
        const resp = await _fetch('/api/auth/session');
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
                    await _fetch('/api/auth/logout', {method: 'POST'});
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
        await _fetch('/api/analytics/track', {
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
