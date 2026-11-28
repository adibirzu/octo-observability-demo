/**
 * Deterministic visual regression coverage for the checkout receipt card (`#checkoutEvidence`).
 *
 * Renders the shop checkout surface offline from local template and token assets,
 * blocks all non-local/provider requests, pins synthetic checkout receipt data,
 * normalizes fonts/animations for repeatable rendering, and verifies both narrow
 * (390x844) and wide (1280x800) viewports against reviewed baselines.
 */

import * as fs from 'fs';
import * as path from 'path';
import { test, expect, Page } from '@playwright/test';

const SHOP_ORIGIN = 'http://shop.example.test';
const SERVER_DIR = path.resolve(__dirname, '../../server');
const BASE_TEMPLATE_PATH = path.join(SERVER_DIR, 'templates/base.html');
const SHOP_TEMPLATE_PATH = path.join(SERVER_DIR, 'templates/shop.html');
const TOKENS_CSS_PATH = path.join(SERVER_DIR, 'static/css/tokens.css');

const TRANSPARENT_PNG_1X1 = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=',
  'base64',
);

const SYNTHETIC_STOREFRONT = {
  products: [
    {
      id: 101,
      sku: 'DRN-SYN-101',
      name: 'Synthetic Survey Quadcopter',
      category: 'Inspection',
      price: 1450,
      stock: 8,
      rating: 4.8,
      inventory_badge: '8 in stock',
      image_url: '/static/img/synthetic-drone.png',
      description: 'Synthetic multi-sensor platform for deterministic visual testing.',
      specs: [
        { label: 'Flight Time', value: '42 min' },
        { label: 'Payload', value: '1.8 kg' },
      ],
    },
  ],
  categories: ['Inspection'],
  stats: {
    product_count: 1,
    order_count: 12,
    revenue: 17400,
  },
  backend: {
    apm_configured: true,
  },
  crm_sync: {
    configured: true,
  },
};

const SYNTHETIC_CART = {
  items: [
    {
      id: 1,
      product_id: 101,
      name: 'Synthetic Survey Quadcopter',
      price: 1450,
      quantity: 1,
      image_url: '/static/img/synthetic-drone.png',
    },
  ],
  total: 1450,
};

const SYNTHETIC_CHECKOUT_RECEIPT = {
  status: 'order_placed',
  order_id: 4201,
  order_status: 'paid',
  payment_status: 'paid',
  payment_required: false,
  total: 1450,
  tracking_number: 'TRK-SYNTH-4201',
  trace_id: '0123456789abcdef0123456789abcdef',
  payment: {
    status: 'authorized',
    provider: 'octo-payment-gateway-emulator',
    method: 'google_pay',
    wallet_type: 'google_pay',
    card_brand: 'mastercard',
    gateway: {
      gateway: 'octo-payment-gateway-emulator',
      request_id: 'pgw-req-synthetic-004201',
      payment_network: 'mastercard',
      steps: [
        { name: 'gateway_payment_received', status: 'ok' },
        { name: 'verification_antifraud_request', status: 'ok' },
        { name: 'verification_antifraud_response', status: 'ok' },
        { name: 'processor_authorization_request', status: 'ok' },
        { name: 'processor_authorization_response', status: 'ok' },
        { name: 'network_authorization_routing', status: 'ok' },
      ],
      final_step: {
        name: 'gateway_authorization_settled',
        status: 'authorized',
      },
      verification: {
        provider: 'octo-antifraud-verification-app',
        status: 'ok',
        decision: 'approved',
      },
    },
  },
};

function extractJinjaBlock(template: string, blockName: string): string {
  const pattern = new RegExp(
    `\\{%\\s*block\\s+${blockName}\\s*%\\}([\\s\\S]*?)\\{%\\s*endblock(?:\\s+${blockName})?\\s*%\\}`,
  );
  const match = template.match(pattern);
  return match ? match[1] : '';
}

function buildShopHtml(): string {
  const baseSource = fs.readFileSync(BASE_TEMPLATE_PATH, 'utf8');
  const shopSource = fs.readFileSync(SHOP_TEMPLATE_PATH, 'utf8');

  const headBlock = extractJinjaBlock(shopSource, 'head');
  const contentBlock = extractJinjaBlock(shopSource, 'content');
  const scriptsBlock = extractJinjaBlock(shopSource, 'scripts');

  let html = baseSource
    .replace(/\{%\s*if\s+rum_configured[\s\S]*?\{%\s*endif\s*%\}/g, '')
    .replace(/\{%\s*if\s+module\s*==\s*'shop'\s*%\}class="active"\s*\{%\s*endif\s*%\}/g, 'class="active" ')
    .replace(/\{%\s*if\s+module\s*==[^%]*%\}[^%]*\{%\s*endif\s*%\}/g, '')
    .replace(/\{%\s*if\s+ai_studio_configured\s+and\s+on_admin_host\s*%\}[\s\S]*?\{%\s*endif\s*%\}/g, '')
    .replace(/\{%\s*block\s+head\s*%\}\s*\{%\s*endblock\s*%\}/, () => headBlock)
    .replace(/\{%\s*block\s+content\s*%\}\s*\{%\s*endblock\s*%\}/, () => contentBlock)
    .replace(/\{%\s*block\s+scripts\s*%\}\s*\{%\s*endblock\s*%\}/, () => scriptsBlock)
    .replace(/\{\{\s*title\s*\}\}/g, 'Drone Shop')
    .replace(/\{\{\s*csp_nonce\s*\}\}/g, 'visual-test-nonce')
    .replace(/\{\{\s*app_name\s*\|\s*tojson\s*\}\}/g, '"octo-drone-shop"')
    .replace(/\{\{\s*java_apm_enabled\s*\|\s*tojson\s*\}\}/g, 'true')
    .replace(/\{\{\s*payment_gateway_simulation_enabled\s*\|\s*tojson\s*\}\}/g, 'true');

  if (/\{%\s*|\s*%\}|\{\{\s*[a-zA-Z_][\w.| ]*\s*\}\}/.test(html)) {
    throw new Error('Unexpanded Jinja tokens remained in rendered shop template');
  }

  return html;
}

function buildSanitizedTokensCss(): string {
  const rawCss = fs.readFileSync(TOKENS_CSS_PATH, 'utf8');
  // Strip external Google Fonts @import so rendering never touches the network.
  return rawCss.replace(/^\s*@import\s+url\([^)]+\);\s*$/gm, '');
}

const RENDERED_SHOP_HTML = buildShopHtml();
const SANITIZED_TOKENS_CSS = buildSanitizedTokensCss();

const DETERMINISTIC_VISUAL_STYLE = `
  *, *::before, *::after {
    animation: none !important;
    transition: none !important;
    caret-color: transparent !important;
  }
  body,
  button,
  input,
  select,
  textarea,
  .btn,
  .brand-copy strong,
  h1,
  h2,
  h3,
  h4,
  .product-price {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif !important;
  }
  code,
  .chip,
  .hero-kicker,
  .mono-label,
  .hero-metric strong,
  .payment-card-preview strong {
    font-family: ui-monospace, "SFMono-Regular", Menlo, Monaco, Consolas, monospace !important;
  }
  .topbar {
    position: static !important;
  }
`;

async function mountDeterministicShop(
  page: Page,
  viewport: { width: number; height: number },
): Promise<string[]> {
  const blockedExternalUrls: string[] = [];

  await page.setViewportSize(viewport);

  await page.route('**/*', async (route) => {
    const requestUrl = route.request().url();
    const parsed = new URL(requestUrl);

    if (parsed.origin !== SHOP_ORIGIN) {
      blockedExternalUrls.push(requestUrl);
      await route.abort('blockedbyclient');
      return;
    }

    if (parsed.pathname === '/shop') {
      await route.fulfill({
        status: 200,
        contentType: 'text/html; charset=utf-8',
        body: RENDERED_SHOP_HTML,
      });
      return;
    }

    if (parsed.pathname === '/static/css/tokens.css') {
      await route.fulfill({
        status: 200,
        contentType: 'text/css; charset=utf-8',
        body: `${SANITIZED_TOKENS_CSS}\n${DETERMINISTIC_VISUAL_STYLE}`,
      });
      return;
    }

    if (parsed.pathname === '/static/js/rum-advanced.js') {
      await route.fulfill({
        status: 200,
        contentType: 'application/javascript; charset=utf-8',
        body: '/* offline stub */',
      });
      return;
    }

    if (parsed.pathname.startsWith('/static/img/')) {
      await route.fulfill({
        status: 200,
        contentType: 'image/png',
        body: TRANSPARENT_PNG_1X1,
      });
      return;
    }

    if (parsed.pathname === '/api/shop/storefront') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(SYNTHETIC_STOREFRONT),
      });
      return;
    }

    if (parsed.pathname === '/api/cart') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(SYNTHETIC_CART),
      });
      return;
    }

    if (parsed.pathname === '/api/shop/locations') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          shops: [
            {
              name: 'OCTO Synthetic Flight Hub',
              address: '100 Telemetry Way, Demo City, DC 00100',
            },
          ],
        }),
      });
      return;
    }

    if (parsed.pathname === '/api/analytics/track') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ status: 'ok' }),
      });
      return;
    }

    if (parsed.pathname === '/api/shop/checkout') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(SYNTHETIC_CHECKOUT_RECEIPT),
      });
      return;
    }

    await route.fulfill({
      status: 404,
      contentType: 'application/json',
      body: JSON.stringify({ error: `Unmapped offline path: ${parsed.pathname}` }),
    });
  });

  await page.goto(`${SHOP_ORIGIN}/shop`, { waitUntil: 'networkidle' });
  await page.evaluate(async () => {
    if (document.fonts && document.fonts.ready) {
      await document.fonts.ready;
    }
  });

  return blockedExternalUrls;
}

async function populateSyntheticReceipt(page: Page): Promise<void> {
  await page.evaluate((receipt) => {
    const w = window as unknown as {
      renderCheckoutEvidence: (payload: unknown) => void;
    };
    w.renderCheckoutEvidence(receipt);
    const status = document.getElementById('checkoutStatus');
    if (status) {
      status.textContent =
        'Order #4201 placed. Payment authorized via octo-payment-gateway-emulator. Gateway 7 steps. Verification approved. Order paid. Tracking: TRK-SYNTH-4201 — Total: $1,450';
    }
  }, SYNTHETIC_CHECKOUT_RECEIPT);

  const receiptCard = page.locator('[data-testid="checkout-evidence"]');
  await expect(receiptCard).toBeVisible();
  await expect(receiptCard.locator('h3')).toHaveText('Checkout receipt');
  await expect(receiptCard.locator('.evidence-row')).toHaveCount(9);
  await expect(receiptCard).toContainText('Trace ID: 0123456789abcdef0123456789abcdef');
  await expect(receiptCard).toContainText('Order ID: 4201');
  await expect(receiptCard).toContainText('Payment Gateway Request ID: pgw-req-synthetic-004201');
  await expect(receiptCard).toContainText('7 token-safe gateway steps captured');
}

test.describe('Checkout receipt card visual regression', () => {
  test('renders populated checkout receipt card deterministically at wide viewport (1280x800)', async ({
    page,
  }) => {
    const blockedExternalUrls = await mountDeterministicShop(page, {
      width: 1280,
      height: 800,
    });
    await populateSyntheticReceipt(page);

    const receiptCard = page.locator('[data-testid="checkout-evidence"]');
    await receiptCard.scrollIntoViewIfNeeded();
    expect(blockedExternalUrls).toEqual([]);

    await expect(receiptCard).toHaveScreenshot('checkout-receipt-wide.png');
  });

  test('renders populated checkout receipt card deterministically at narrow viewport (390x844)', async ({
    page,
  }) => {
    const blockedExternalUrls = await mountDeterministicShop(page, {
      width: 390,
      height: 844,
    });
    await populateSyntheticReceipt(page);

    const receiptCard = page.locator('[data-testid="checkout-evidence"]');
    await receiptCard.scrollIntoViewIfNeeded();
    expect(blockedExternalUrls).toEqual([]);

    await expect(receiptCard).toHaveScreenshot('checkout-receipt-narrow.png');
  });
});
