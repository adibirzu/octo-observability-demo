/* Enterprise CRM Portal — Frontend JavaScript */

// Check session on page load
(async function checkSession() {
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
                loginBtn.onclick = async (e) => {
                    e.preventDefault();
                    await fetch('/api/auth/logout', {method: 'POST'});
                    window.location.href = '/login';
                };
            }
        }
    } catch (e) {
        console.error('Session check failed:', e);
    }
})();
