/*
 * Enterprise CRM Portal — k6 Load Test
 *
 * Multi-location end-to-end testing for performance and security.
 * Inspired by: https://grafana.com/blog/load-testing-websites/
 *
 * Usage:
 *   k6 run --env BASE_URL=http://localhost:8080 k6/load_test.js
 *   k6 run --env BASE_URL=https://crm.example.com k6/load_test.js
 *
 * k6 Cloud (multi-location):
 *   k6 cloud k6/load_test.js
 */

import http from 'k6/http';
import { check, group, sleep } from 'k6';
import { Rate, Trend, Counter } from 'k6/metrics';

// Custom metrics
const errorRate = new Rate('errors');
const loginDuration = new Trend('login_duration');
const dashboardDuration = new Trend('dashboard_duration');
const searchDuration = new Trend('search_duration');
const apiCalls = new Counter('api_calls');

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8080';

export const options = {
    // Ramp-up scenario simulating real user patterns
    scenarios: {
        // Normal browsing users
        browse: {
            executor: 'ramping-vus',
            startVUs: 1,
            stages: [
                { duration: '30s', target: 5 },
                { duration: '1m', target: 15 },
                { duration: '2m', target: 25 },
                { duration: '30s', target: 5 },
                { duration: '10s', target: 0 },
            ],
            gracefulRampDown: '10s',
        },
        // API load (higher throughput)
        api_load: {
            executor: 'constant-arrival-rate',
            rate: 20,
            timeUnit: '1s',
            duration: '3m',
            preAllocatedVUs: 10,
            maxVUs: 30,
            startTime: '30s', // start after browse ramp-up
        },
        // Attack simulation (SQLi, XSS probes)
        security_probes: {
            executor: 'per-vu-iterations',
            vus: 3,
            iterations: 50,
            startTime: '1m',
        },
    },
    thresholds: {
        http_req_duration: ['p(95)<3000', 'p(99)<5000'],
        errors: ['rate<0.1'],
        login_duration: ['p(95)<2000'],
        dashboard_duration: ['p(95)<3000'],
    },
};

// ── Browsing Scenario ───────────────────────────────────────────

export default function() {
    group('User Journey', () => {
        // 1. Load landing page
        group('Landing Page', () => {
            const res = http.get(`${BASE_URL}/`);
            check(res, { 'landing page loads': (r) => r.status === 200 });
            errorRate.add(res.status !== 200);
            apiCalls.add(1);
            sleep(1);
        });

        // 2. Login
        group('Login', () => {
            const start = Date.now();
            const res = http.post(`${BASE_URL}/api/auth/login`,
                JSON.stringify({ username: 'admin', password: 'admin123' }),
                { headers: { 'Content-Type': 'application/json' } }
            );
            loginDuration.add(Date.now() - start);
            check(res, { 'login succeeds': (r) => r.status === 200 });
            errorRate.add(res.status !== 200);
            apiCalls.add(1);
            sleep(0.5);
        });

        // 3. Dashboard
        group('Dashboard', () => {
            const start = Date.now();
            const res = http.get(`${BASE_URL}/api/dashboard/summary`);
            dashboardDuration.add(Date.now() - start);
            check(res, { 'dashboard loads': (r) => r.status === 200 });
            errorRate.add(res.status !== 200);
            apiCalls.add(1);
            sleep(2);
        });

        // 4. Browse customers
        group('Customers', () => {
            const res = http.get(`${BASE_URL}/api/customers`);
            check(res, { 'customers list loads': (r) => r.status === 200 });
            apiCalls.add(1);
            sleep(1);

            // View a specific customer
            const detail = http.get(`${BASE_URL}/api/customers/1`);
            check(detail, { 'customer detail loads': (r) => r.status === 200 });
            apiCalls.add(1);
            sleep(1);
        });

        // 5. Search customers
        group('Search', () => {
            const start = Date.now();
            const res = http.get(`${BASE_URL}/api/customers?search=Acme`);
            searchDuration.add(Date.now() - start);
            check(res, { 'search works': (r) => r.status === 200 });
            apiCalls.add(1);
            sleep(1);
        });

        // 6. Browse orders
        group('Orders', () => {
            const res = http.get(`${BASE_URL}/api/orders`);
            check(res, { 'orders list loads': (r) => r.status === 200 });
            apiCalls.add(1);
            sleep(1);
        });

        // 7. Browse products
        group('Products', () => {
            const res = http.get(`${BASE_URL}/api/products`);
            check(res, { 'products list loads': (r) => r.status === 200 });
            apiCalls.add(1);
            sleep(1);
        });

        // 8. Check invoices
        group('Invoices', () => {
            const res = http.get(`${BASE_URL}/api/invoices`);
            check(res, { 'invoices list loads': (r) => r.status === 200 });
            apiCalls.add(1);
            sleep(1);
        });

        // 9. Support tickets
        group('Tickets', () => {
            const res = http.get(`${BASE_URL}/api/tickets`);
            check(res, { 'tickets list loads': (r) => r.status === 200 });
            apiCalls.add(1);
            sleep(1);
        });

        // 10. Health check
        group('Health', () => {
            const res = http.get(`${BASE_URL}/health`);
            check(res, { 'health ok': (r) => r.status === 200 });
            apiCalls.add(1);
        });
    });
}

// ── API Load Scenario ───────────────────────────────────────────

export function api_load() {
    const endpoints = [
        '/api/dashboard/summary',
        '/api/customers',
        '/api/orders',
        '/api/products',
        '/api/invoices',
        '/api/tickets',
        '/health',
        '/ready',
    ];

    const endpoint = endpoints[Math.floor(Math.random() * endpoints.length)];
    const res = http.get(`${BASE_URL}${endpoint}`);
    check(res, { 'api responds': (r) => r.status === 200 });
    errorRate.add(res.status !== 200);
    apiCalls.add(1);
}

// ── Security Probes Scenario ────────────────────────────────────

export function security_probes() {
    const attacks = [
        // SQLi probes
        { url: `/api/customers?search=' OR '1'='1`, name: 'sqli_basic' },
        { url: `/api/customers?search=' UNION SELECT * FROM users--`, name: 'sqli_union' },
        { url: `/api/customers?sort_by=name; DROP TABLE customers`, name: 'sqli_drop' },
        { url: `/api/products?category=' OR 1=1--`, name: 'sqli_products' },

        // XSS probes
        { url: `/api/tickets?search=<script>alert(1)</script>`, name: 'xss_reflected' },
        { url: `/api/customers?search=<img onerror=alert(1) src=x>`, name: 'xss_img' },

        // Path traversal
        { url: `/api/files/download?path=../../../etc/passwd`, name: 'path_traversal' },

        // SSRF
        {
            url: `/api/files/import-url`,
            name: 'ssrf_metadata',
            method: 'POST',
            body: JSON.stringify({ url: 'http://192.0.2.40/latest/meta-data/' }),
        },

        // Admin access (no auth)
        { url: `/api/admin/config`, name: 'admin_config_access' },
        { url: `/api/admin/users`, name: 'admin_user_list' },
    ];

    const attack = attacks[Math.floor(Math.random() * attacks.length)];

    let res;
    if (attack.method === 'POST') {
        res = http.post(`${BASE_URL}${attack.url}`, attack.body, {
            headers: { 'Content-Type': 'application/json' },
            tags: { attack_type: attack.name },
        });
    } else {
        res = http.get(`${BASE_URL}${attack.url}`, {
            tags: { attack_type: attack.name },
        });
    }

    apiCalls.add(1);
    sleep(0.5);
}
