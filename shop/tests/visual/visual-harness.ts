/**
 * Shared deterministic visual regression harness helpers for offline Playwright specs.
 *
 * Centralizes Jinja block extraction, external `@import` CSS stripping, deterministic
 * system-font/animation/caret overrides, and offline route mounting with foreign-origin
 * request blocking so visual regression suites stay DRY and repeatable.
 */

import * as fs from 'fs';
import { Page, Route } from '@playwright/test';

export const VISUAL_TEST_ORIGIN = 'http://shop.example.test';

export const TRANSPARENT_PNG_1X1 = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=',
  'base64',
);

export const SYSTEM_SANS_FONT_STACK =
  '-apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif';

export const SYSTEM_MONO_FONT_STACK =
  'ui-monospace, "SFMono-Regular", Menlo, Monaco, Consolas, monospace';

export function extractJinjaBlock(template: string, blockName: string): string {
  const pattern = new RegExp(
    `\\{%\\s*block\\s+${blockName}\\s*%\\}([\\s\\S]*?)\\{%\\s*endblock(?:\\s+${blockName})?\\s*%\\}`,
  );
  const match = template.match(pattern);
  return match ? match[1] : '';
}

export function assertNoUnexpandedJinjaTokens(html: string, templateLabel: string): void {
  if (/\{%\s*|\s*%\}|\{\{\s*[a-zA-Z_][\w.| ]*\s*\}\}/.test(html)) {
    throw new Error(`Unexpanded Jinja tokens remained in rendered ${templateLabel} template`);
  }
}

export function stripExternalCssImports(cssContent: string): string {
  // Strip external @import rules so rendering never touches the network.
  return cssContent.replace(/^\s*@import\s+url\([^)]+\);\s*$/gm, '');
}

export function loadSanitizedCssFile(cssFilePath: string): string {
  return stripExternalCssImports(fs.readFileSync(cssFilePath, 'utf8'));
}

export interface DeterministicStyleOptions {
  sansSelectors: readonly string[];
  monoSelectors: readonly string[];
  extraCss?: string;
}

export function buildDeterministicVisualStyle(options: DeterministicStyleOptions): string {
  const sansRule = `${options.sansSelectors.join(',\n  ')} {\n    font-family: ${SYSTEM_SANS_FONT_STACK} !important;\n  }`;
  const monoRule = `${options.monoSelectors.join(',\n  ')} {\n    font-family: ${SYSTEM_MONO_FONT_STACK} !important;\n  }`;
  const extra = options.extraCss ? `\n  ${options.extraCss.trim()}` : '';

  return `
  *, *::before, *::after {
    animation: none !important;
    transition: none !important;
    caret-color: transparent !important;
  }
  ${sansRule}
  ${monoRule}${extra}
`;
}

export interface OfflineRouteResponse {
  status?: number;
  contentType: string;
  body: string | Buffer;
}

export type OfflinePathHandler = (
  pathname: string,
  parsedUrl: URL,
  route: Route,
) => OfflineRouteResponse | Promise<OfflineRouteResponse | null> | null;

export interface MountOfflinePageOptions {
  page: Page;
  viewport: { width: number; height: number };
  entryPath: string;
  origin?: string;
  resolvePath: OfflinePathHandler;
}

/**
 * Mounts an offline page at `${origin}${entryPath}`, blocking any foreign-origin requests,
 * serving `/static/img/*` with a 1x1 transparent PNG by default unless overridden, returning
 * an intercepted 404 JSON response for unmapped same-origin paths, and awaiting `document.fonts.ready`.
 */
export async function mountOfflineVisualPage(options: MountOfflinePageOptions): Promise<string[]> {
  const origin = options.origin ?? VISUAL_TEST_ORIGIN;
  const blockedExternalUrls: string[] = [];

  await options.page.setViewportSize(options.viewport);

  await options.page.route('**/*', async (route) => {
    const requestUrl = route.request().url();
    const parsed = new URL(requestUrl);

    if (parsed.origin !== origin) {
      blockedExternalUrls.push(requestUrl);
      await route.abort('blockedbyclient');
      return;
    }

    const customResponse = await options.resolvePath(parsed.pathname, parsed, route);
    if (customResponse) {
      await route.fulfill({
        status: customResponse.status ?? 200,
        contentType: customResponse.contentType,
        body: customResponse.body,
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

    await route.fulfill({
      status: 404,
      contentType: 'application/json',
      body: JSON.stringify({ error: `Unmapped offline path: ${parsed.pathname}` }),
    });
  });

  await options.page.goto(`${origin}${options.entryPath}`, { waitUntil: 'networkidle' });
  await options.page.evaluate(async () => {
    if (document.fonts && document.fonts.ready) {
      await document.fonts.ready;
    }
  });

  return blockedExternalUrls;
}
