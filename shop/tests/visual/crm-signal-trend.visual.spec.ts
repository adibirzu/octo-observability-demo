/**
 * Deterministic visual regression coverage for the CRM Signal Trend card (`#signal-trend`).
 *
 * Renders the CRM observability surface offline from bundled CRM template and stylesheet assets,
 * blocks all non-local/provider requests, pins synthetic signal trend payloads across four states
 * (ordered samples, observed zero, null gaps, Missing), normalizes fonts/animations for repeatable
 * rendering, and verifies both wide (1280x800) and narrow (390x844) viewports against reviewed baselines.
 */

import * as fs from 'fs';
import * as path from 'path';
import { test, expect, Page } from '@playwright/test';

const CRM_ORIGIN = 'http://shop.example.test';
const CRM_SERVER_DIR = path.resolve(__dirname, '../../../crm/server');
const CRM_BASE_TEMPLATE_PATH = path.join(CRM_SERVER_DIR, 'templates/base.html');
const CRM_OBSERVABILITY_TEMPLATE_PATH = path.join(CRM_SERVER_DIR, 'templates/observability.html');
const CRM_STYLE_CSS_PATH = path.join(CRM_SERVER_DIR, 'static/css/style.css');
const CRM_APP_JS_PATH = path.join(CRM_SERVER_DIR, 'static/js/app.js');

const TRANSPARENT_PNG_1X1 = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=',
  'base64',
);

interface TrendSample {
  time: string;
  value: number | null;
}

interface TrendStateCase {
  slug: 'ordered-samples' | 'observed-zero' | 'null-gaps' | 'missing';
  label: string;
  trend: { samples?: TrendSample[] } | null;
  expectedChip: 'Observed' | 'Partial' | 'Missing';
  expectedSummaryText: string;
  expectedCircleCount: number;
  expectedLineCount: number;
  expectedCircleCoords?: Array<{ cx: string; cy: string }>;
}

const TREND_STATE_CASES: readonly TrendStateCase[] = [
  {
    slug: 'ordered-samples',
    label: 'ordered samples',
    trend: {
      samples: [
        { time: '10:00Z', value: 12 },
        { time: '10:05Z', value: 18 },
        { time: '10:10Z', value: 15 },
        { time: '10:15Z', value: 24 },
      ],
    },
    expectedChip: 'Observed',
    expectedSummaryText:
      'Signal samples (4 of 4 observed): 10:00Z: 12; 10:05Z: 18; 10:10Z: 15; 10:15Z: 24',
    expectedCircleCount: 4,
    expectedLineCount: 3,
    expectedCircleCoords: [
      { cx: '0', cy: '45' },
      { cx: '33.333333333333336', cy: '25' },
      { cx: '66.66666666666667', cy: '35' },
      { cx: '100', cy: '5' },
    ],
  },
  {
    slug: 'observed-zero',
    label: 'observed zero',
    trend: {
      samples: [
        { time: '10:00Z', value: 0 },
        { time: '10:05Z', value: 0 },
        { time: '10:10Z', value: 0 },
        { time: '10:15Z', value: 0 },
      ],
    },
    expectedChip: 'Observed',
    expectedSummaryText:
      'Signal samples (4 of 4 observed): 10:00Z: 0; 10:05Z: 0; 10:10Z: 0; 10:15Z: 0',
    expectedCircleCount: 4,
    expectedLineCount: 3,
    expectedCircleCoords: [
      { cx: '0', cy: '25' },
      { cx: '33.333333333333336', cy: '25' },
      { cx: '66.66666666666667', cy: '25' },
      { cx: '100', cy: '25' },
    ],
  },
  {
    slug: 'null-gaps',
    label: 'null gaps',
    trend: {
      samples: [
        { time: '10:00Z', value: 10 },
        { time: '10:05Z', value: null },
        { time: '10:10Z', value: 20 },
        { time: '10:15Z', value: 30 },
      ],
    },
    expectedChip: 'Partial',
    expectedSummaryText:
      'Signal samples (3 of 4 observed): 10:00Z: 10; 10:05Z: missing; 10:10Z: 20; 10:15Z: 30',
    expectedCircleCount: 3,
    expectedLineCount: 1,
    expectedCircleCoords: [
      { cx: '0', cy: '45' },
      { cx: '66.66666666666667', cy: '25.000000000000004' },
      { cx: '100', cy: '5' },
    ],
  },
  {
    slug: 'missing',
    label: 'Missing',
    trend: {
      samples: [],
    },
    expectedChip: 'Missing',
    expectedSummaryText: 'No valid bounded trend samples supplied.',
    expectedCircleCount: 0,
    expectedLineCount: 0,
  },
];

function extractJinjaBlock(template: string, blockName: string): string {
  const pattern = new RegExp(
    `\\{%\\s*block\\s+${blockName}\\s*%\\}([\\s\\S]*?)\\{%\\s*endblock(?:\\s+${blockName})?\\s*%\\}`,
  );
  const match = template.match(pattern);
  return match ? match[1] : '';
}

function buildCrmObservabilityHtml(): string {
  const baseSource = fs.readFileSync(CRM_BASE_TEMPLATE_PATH, 'utf8');
  const obsSource = fs.readFileSync(CRM_OBSERVABILITY_TEMPLATE_PATH, 'utf8');

  const headerActionsBlock = extractJinjaBlock(obsSource, 'header_actions');
  const contentBlock = extractJinjaBlock(obsSource, 'content');
  const scriptsBlock = extractJinjaBlock(obsSource, 'scripts');

  let html = baseSource
    .replace(/\{%\s*if\s+rum_configured\s*%\}[\s\S]*?\{%\s*endif\s*%\}/g, '')
    .replace(/\{%\s*if\s+apm_console_url\s*%\}[\s\S]*?\{%\s*endif\s*%\}/g, '')
    .replace(/\{%\s*if\s+log_analytics_console_url\s*%\}[\s\S]*?\{%\s*endif\s*%\}/g, '')
    .replace(
      /\{%\s*if\s+nav_key\s*==\s*'observability'\s*%\}active\{%\s*endif\s*%\}/g,
      'active',
    )
    .replace(/\{%\s*if\s+nav_key\s*==[^%]*%\}[^%]*\{%\s*endif\s*%\}/g, '')
    .replace(
      /\{%\s*block\s+header_actions\s*%\}\s*\{%\s*endblock\s*%\}/,
      () => headerActionsBlock,
    )
    .replace(/\{%\s*block\s+content\s*%\}\s*\{%\s*endblock\s*%\}/, () => contentBlock)
    .replace(/\{%\s*block\s+scripts\s*%\}\s*\{%\s*endblock\s*%\}/, () => scriptsBlock)
    .replace(/\{\{\s*title\s*\}\}/g, 'OCI Observability 360')
    .replace(/\{\{\s*brand_name\s*\}\}/g, 'OCTO Enterprise CRM')
    .replace(/\{\{\s*app_version\s*\}\}/g, '1.0.0')
    .replace(
      /\{\{\s*request\.state\.csp_nonce\s+if\s+request\s+and\s+request\.state\s+and\s+request\.state\.csp_nonce\s+else\s+''\s*\}\}/g,
      'visual-test-nonce',
    )
    .replace(/\{\{\s*app_name\s*\|\s*tojson\s*\}\}/g, '"enterprise-crm-portal"')
    .replace(/\{\{\s*brand_name\s*\|\s*tojson\s*\}\}/g, '"OCTO Enterprise CRM"')
    .replace(/\{\{\s*app_version\s*\|\s*tojson\s*\}\}/g, '"1.0.0"')
    .replace(/\{\{\s*apm_console_url\s*\|\s*tojson\s*\}\}/g, '""')
    .replace(/\{\{\s*opsi_console_url\s*\|\s*tojson\s*\}\}/g, '""')
    .replace(/\{\{\s*db_management_console_url\s*\|\s*tojson\s*\}\}/g, '""')
    .replace(/\{\{\s*log_analytics_console_url\s*\|\s*tojson\s*\}\}/g, '""');

  if (/\{%\s*|\s*%\}|\{\{\s*[a-zA-Z_][\w.| ]*\s*\}\}/.test(html)) {
    throw new Error('Unexpanded Jinja tokens remained in rendered CRM observability template');
  }

  return html;
}

function buildSanitizedCrmCss(): string {
  const rawCss = fs.readFileSync(CRM_STYLE_CSS_PATH, 'utf8');
  return rawCss.replace(/^\s*@import\s+url\([^)]+\);\s*$/gm, '');
}

const RENDERED_CRM_OBSERVABILITY_HTML = buildCrmObservabilityHtml();
const SANITIZED_CRM_CSS = buildSanitizedCrmCss();
const CRM_APP_JS = fs.readFileSync(CRM_APP_JS_PATH, 'utf8');

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
  .sidebar-header h2,
  h1,
  h2,
  h3,
  h4,
  p,
  span,
  strong {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif !important;
  }
  code,
  pre,
  .code-output,
  .panel-chip,
  .section-kicker,
  .eyebrow {
    font-family: ui-monospace, "SFMono-Regular", Menlo, Monaco, Consolas, monospace !important;
  }
`;

function buildSyntheticObservability360Payload(trend: { samples?: TrendSample[] } | null) {
  return {
    timestamp: null,
    demo: {
      badge: 'Demo project',
      name: 'OCI Observability Demo',
      description: 'Synthetic customer experience telemetry for deterministic visual regression.',
      privacy_note: 'Technical identifiers and infrastructure settings are intentionally hidden.',
    },
    hero: {
      status: 'Healthy',
      summary: 'Synthetic MELT signals active across storefront and CRM.',
      active_signals: 6,
      total_signals: 6,
      tone: 'success',
    },
    scorecards: [
      { label: 'Active Customers', value: 128, format: 'number', tone: 'accent' },
      { label: 'Orders Synced', value: 42, format: 'number', tone: 'success' },
    ],
    charts: {
      business_mix: [{ label: 'Storefront Checkout', value: 42, tone: 'accent' }],
      order_flow: [{ label: 'Paid & Synced', value: 42, tone: 'success' }],
      signal_coverage: [
        {
          label: 'Distributed Tracing',
          service: 'OCI APM',
          description: 'End-to-end W3C trace propagation across shop and CRM.',
          active: true,
          tone: 'success',
        },
      ],
      signal_trend: trend,
    },
    customer_journey: [
      {
        label: 'Checkout to CRM Handoff',
        metric: '42 synced orders',
        status: 'Healthy',
        tone: 'success',
      },
    ],
    service_health: {
      crm: {
        label: 'Enterprise CRM Portal',
        status: 'Healthy',
        tone: 'success',
        latency_ms: 14.2,
        success_rate: 100.0,
      },
    },
  };
}

async function mountDeterministicCrmObservability(
  page: Page,
  viewport: { width: number; height: number },
  stateCase: TrendStateCase,
): Promise<string[]> {
  const blockedExternalUrls: string[] = [];
  const payload = buildSyntheticObservability360Payload(stateCase.trend);

  await page.setViewportSize(viewport);

  await page.route('**/*', async (route) => {
    const requestUrl = route.request().url();
    const parsed = new URL(requestUrl);

    if (parsed.origin !== CRM_ORIGIN) {
      blockedExternalUrls.push(requestUrl);
      await route.abort('blockedbyclient');
      return;
    }

    if (parsed.pathname === '/observability') {
      await route.fulfill({
        status: 200,
        contentType: 'text/html; charset=utf-8',
        body: RENDERED_CRM_OBSERVABILITY_HTML,
      });
      return;
    }

    if (parsed.pathname === '/static/css/style.css') {
      await route.fulfill({
        status: 200,
        contentType: 'text/css; charset=utf-8',
        body: `${SANITIZED_CRM_CSS}\n${DETERMINISTIC_VISUAL_STYLE}`,
      });
      return;
    }

    if (parsed.pathname === '/static/js/app.js') {
      await route.fulfill({
        status: 200,
        contentType: 'application/javascript; charset=utf-8',
        body: CRM_APP_JS,
      });
      return;
    }

    if (
      parsed.pathname === '/static/js/observability.js' ||
      parsed.pathname === '/static/js/rum-advanced.js'
    ) {
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

    if (parsed.pathname === '/api/observability/360') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(payload),
      });
      return;
    }

    if (parsed.pathname === '/api/auth/session') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ authenticated: false }),
      });
      return;
    }

    if (
      parsed.pathname === '/api/analytics/track' ||
      parsed.pathname === '/api/observability/frontend'
    ) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ status: 'ok' }),
      });
      return;
    }

    await route.fulfill({
      status: 404,
      contentType: 'application/json',
      body: JSON.stringify({ error: `Unmapped offline path: ${parsed.pathname}` }),
    });
  });

  await page.goto(`${CRM_ORIGIN}/observability`, { waitUntil: 'networkidle' });
  await page.evaluate(async () => {
    if (document.fonts && document.fonts.ready) {
      await document.fonts.ready;
    }
  });

  const trendSection = page.locator('section[aria-labelledby="signal-trend-title"]');
  await expect(trendSection).toBeVisible();
  await expect(trendSection.locator('#signal-trend-title')).toHaveText('Signal Trend');
  await expect(trendSection.locator('#signal-trend .panel-chip')).toHaveText(
    stateCase.expectedChip,
  );
  await expect(trendSection.locator('#signal-trend p')).toHaveText(stateCase.expectedSummaryText);
  await expect(trendSection.locator('#signal-trend svg circle')).toHaveCount(
    stateCase.expectedCircleCount,
  );
  await expect(trendSection.locator('#signal-trend svg line')).toHaveCount(
    stateCase.expectedLineCount,
  );

  if (stateCase.expectedCircleCoords) {
    const coords = await trendSection
      .locator('#signal-trend svg circle')
      .evaluateAll((circles) =>
        circles.map((el) => ({
          cx: el.getAttribute('cx') || '',
          cy: el.getAttribute('cy') || '',
        })),
      );
    expect(coords).toEqual(stateCase.expectedCircleCoords);
  }

  return blockedExternalUrls;
}

const VIEWPORTS = [
  { name: 'wide', width: 1280, height: 800 },
  { name: 'narrow', width: 390, height: 844 },
] as const;

test.describe('CRM Signal Trend card visual regression', () => {
  for (const stateCase of TREND_STATE_CASES) {
    for (const vp of VIEWPORTS) {
      test(`renders CRM Signal Trend card for ${stateCase.label} state at ${vp.name} viewport (${vp.width}x${vp.height})`, async ({
        page,
      }) => {
        const blockedExternalUrls = await mountDeterministicCrmObservability(
          page,
          { width: vp.width, height: vp.height },
          stateCase,
        );

        const trendSection = page.locator('section[aria-labelledby="signal-trend-title"]');
        await trendSection.scrollIntoViewIfNeeded();
        expect(blockedExternalUrls).toEqual([]);

        await expect(trendSection).toHaveScreenshot(
          `crm-signal-trend-${stateCase.slug}-${vp.name}.png`,
        );
      });
    }
  }
});
