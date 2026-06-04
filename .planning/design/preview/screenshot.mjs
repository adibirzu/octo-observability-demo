// WS4c preview harness — screenshot rendered pages at responsive breakpoints.
// Usage: node screenshot.mjs <baseUrl> <label> <page> [widths...]
//   node screenshot.mjs http://localhost:8099 before dashboard.html 1440 768
import { createRequire } from 'node:module';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import fs from 'node:fs';

// Resolve playwright from the shop app's node_modules regardless of script cwd.
const require = createRequire('/Users/abirzu/dev/octo-observability-demo/shop/package.json');
const { chromium } = require('playwright');

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const OUT = path.join(__dirname, 'shots');
fs.mkdirSync(OUT, { recursive: true });

const [baseUrl, label, page = 'dashboard.html', ...widthArgs] = process.argv.slice(2);
const widths = (widthArgs.length ? widthArgs : ['1440', '768']).map(Number);

const browser = await chromium.launch();
const slug = page.replace(/\.html$/, '');
for (const w of widths) {
  const ctx = await browser.newContext({ viewport: { width: w, height: 1000 }, deviceScaleFactor: 1 });
  const p = await ctx.newPage();
  const url = `${baseUrl}/_preview/${page}`;
  await p.goto(url, { waitUntil: 'networkidle' }).catch(() => p.goto(url));
  await p.waitForTimeout(700); // let JS render the tiles
  const file = path.join(OUT, `${slug}-${label}-${w}.png`);
  await p.screenshot({ path: file, fullPage: true });
  console.log(`shot ${file}`);
  await ctx.close();
}
await browser.close();
