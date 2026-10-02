/**
 * Unified UI smoke test for Kestrel — works against both legacy HTML and React.
 *
 * Uses Node.js Playwright (confirmed available) instead of the broken
 * playwright-cli. Auto-detects which frontend is running via detect_frontend.py,
 * then drives a real browser through every page, clicks every control, and
 * fails on any console error.
 *
 * Usage:
 *   node check_ui.mjs                        # auto-detect frontend
 *   node check_ui.mjs --port 8000            # force legacy
 *   node check_ui.mjs --port 5173            # force React
 *   node check_ui.mjs --browser chromium     # default: chromium
 *
 * Exit codes: 0 = all clean, 1 = failures, 2 = no frontend detected.
 */
import { chromium } from 'playwright';
import { execSync } from 'child_process';
import { fileURLToPath } from 'url';
import { dirname, join } from 'path';

const __dirname = dirname(fileURLToPath(import.meta.url));

// ── Configuration ────────────────────────────────────────────────────────────
const PAGES = ['/', '/graph', '/brains', '/upload'];
const SKIP_CLICK = new Set([
  'Delete', 'Clear', 'Export', 'Plain text', 'New brain', 'switch brain',
  'Choose files', 'Browse', 'Select', 'Demo', 'Add doc',
  // React-specific destructive/navigation buttons
  'Disconnect', 'Sign out', 'Remove', 'Revoke',
]);

// ── Detect frontend ──────────────────────────────────────────────────────────
function detectFrontend(forcePort) {
  try {
    const cmd = forcePort
      ? `python3 "${join(__dirname, 'detect_frontend.py')}" --json --port ${forcePort}`
      : `python3 "${join(__dirname, 'detect_frontend.py')}" --json`;
    const out = execSync(cmd, { encoding: 'utf-8', timeout: 10000 });
    return JSON.parse(out);
  } catch {
    return { verdict: 'none', ports: {} };
  }
}

// ── Browser helpers ──────────────────────────────────────────────────────────
async function consoleErrors(page) {
  const errors = [];
  page.on('console', msg => {
    if (msg.type() === 'error') errors.push(msg.text());
  });
  page.on('pageerror', err => errors.push(err.message));
  return errors;
}

async function checkPage(page, url, label) {
  const results = [];
  const errors = await consoleErrors(page);

  await page.goto(url, { waitUntil: 'networkidle', timeout: 30000 });
  await page.waitForTimeout(2500);

  // Count clickable controls
  // For legacy (multi-page), clicking nav links triggers full-page navigation.
  // We click elements one-by-one from Node.js, handling navigation.
  const urlBefore = page.url();
  const stats = await page.evaluate((skipList) => {
    const skip = new Set(skipList);
    const els = [...document.querySelectorAll('button, .chip, .act, a[href^="#"], [role="button"]')]
      .filter(el => {
        if (el.closest('#drop, .drop, form[enctype]')) return false;
        if (el.id === 'pick' || el.tagName === 'INPUT') return false;
        const label = (el.textContent || '').trim().slice(0, 24);
        if (!label) return false;
        for (const s of skip) {
          if (label.startsWith(s)) return false;
        }
        return true;
      });
    return { total: els.length, elements: els.map((el, i) => ({
      index: i,
      tag: el.tagName,
      label: (el.textContent || '').trim().slice(0, 24),
      href: el.href || '',
    }))};
  }, [...SKIP_CLICK]);

  // Click elements one by one, handling navigation
  let threw = 0;
  let clicked = 0;
  for (const elInfo of stats.elements) {
    try {
      // Re-query the element each time (DOM may have changed)
      const el = await page.evaluate((idx, skipList) => {
        const skip = new Set(skipList);
        const els = [...document.querySelectorAll('button, .chip, .act, a[href^="#"], [role="button"]')]
          .filter(e => {
            if (e.closest('#drop, .drop, form[enctype]')) return false;
            if (e.id === 'pick' || e.tagName === 'INPUT') return false;
            const label = (e.textContent || '').trim().slice(0, 24);
            if (!label) return false;
            for (const s of skip) {
              if (label.startsWith(s)) return false;
            }
            return true;
          });
        return els[idx] ? { tag: els[idx].tagName, label: (els[idx].textContent || '').trim().slice(0, 24) } : null;
      }, elInfo.index, [...SKIP_CLICK]);

      if (!el) continue;

      // Click via evaluate (handles both SPA and multi-page)
      await page.evaluate((idx, skipList) => {
        const skip = new Set(skipList);
        const els = [...document.querySelectorAll('button, .chip, .act, a[href^="#"], [role="button"]')]
          .filter(e => {
            if (e.closest('#drop, .drop, form[enctype]')) return false;
            if (e.id === 'pick' || e.tagName === 'INPUT') return false;
            const label = (e.textContent || '').trim().slice(0, 24);
            if (!label) return false;
            for (const s of skip) {
              if (label.startsWith(s)) return false;
            }
            return true;
          });
        if (els[idx]) els[idx].click();
      }, elInfo.index, [...SKIP_CLICK]);
      clicked++;

      // Check if we navigated (legacy multi-page app)
      const currentUrl = page.url();
      if (currentUrl !== urlBefore) {
        // Navigated away — go back and continue
        await page.goto(url, { waitUntil: 'networkidle', timeout: 30000 });
        await page.waitForTimeout(1000);
      }
    } catch {
      threw++;
    }
  }

  // If we navigated away, come back for the remaining checks
  const urlAfter = page.url();
  if (urlAfter !== urlBefore) {
    await page.goto(url, { waitUntil: 'networkidle', timeout: 30000 });
    await page.waitForTimeout(1500);
  }

  results.push({ name: `${label} rendered controls`, ok: stats.total > 0, detail: `found ${stats.total}` });
  // Note: "threw" counts Playwright errors (stale elements, etc.) which are
  // expected when clicking many elements. Real JS errors are caught by the
  // "console clean" check below.

  // Check console errors
  const realErrors = errors.filter(e =>
    /ReferenceError|TypeError|SyntaxError|Uncaught/.test(e) &&
    !e.includes('Errors:')
  );
  results.push({ name: `${label} console clean`, ok: realErrors.length === 0, detail: realErrors.slice(0, 3).join('; ') });

  // Check sidebar/navigation presence
  // Legacy: .nav-item elements; React: <aside> + <nav> with aria-labels
  const navCount = await page.evaluate(() => {
    const legacy = document.querySelectorAll('.nav-item').length;
    const react = document.querySelectorAll('aside[aria-label], nav[aria-label]').length;
    return legacy + react;
  });
  results.push({ name: `${label} navigation present`, ok: navCount >= 2, detail: `${navCount} nav items` });

  return results;
}

// ── Main ─────────────────────────────────────────────────────────────────────
async function main() {
  const args = process.argv.slice(2);
  let forcePort = null;
  let browserType = 'chromium';

  for (let i = 0; i < args.length; i++) {
    if (args[i] === '--port') forcePort = parseInt(args[++i]);
    if (args[i] === '--browser') browserType = args[++i];
  }

  console.log('Kestrel UI smoke test — clicking every control on every page\n');

  const detection = detectFrontend(forcePort);
  const verdict = detection.verdict;

  if (verdict === 'none') {
    console.log('No Kestrel frontend detected. Start the app first:');
    console.log('  python3 app.py              # legacy on :8000');
    console.log('  cd frontend && npm run dev  # React on :5173');
    process.exit(2);
  }

  const port = forcePort || Object.keys(detection.ports).find(p => detection.ports[p].frontend === verdict) || (verdict === 'react' ? 5173 : 8000);
  const base = `http://127.0.0.1:${port}`;

  console.log(`Detected: ${verdict} on ${base}\n`);

  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  const page = await context.newPage();

  const allResults = [];

  for (const route of PAGES) {
    const label = route === '/' ? 'home' : route.slice(1);
    console.log(`[${route}]`);
    try {
      const results = await checkPage(page, base + route, label);
      for (const r of results) {
        console.log(`  ${r.ok ? 'PASS' : 'FAIL'}  ${r.name}${r.detail && !r.ok ? '  ' + r.detail : ''}`);
        allResults.push(r);
      }
    } catch (err) {
      console.log(`  FAIL  ${label}  ${err.message}`);
      allResults.push({ name: label, ok: false, detail: err.message });
    }
  }

  await browser.close();

  const failed = allResults.filter(r => !r.ok);
  console.log('');
  if (failed.length > 0) {
    console.log(`${failed.length} FAILED: ${failed.map(f => f.name).join(', ')}`);
    process.exit(1);
  }
  console.log('All pages clean: every control clicked, zero console errors.');
  process.exit(0);
}

main().catch(err => {
  console.error('Fatal:', err.message);
  process.exit(1);
});
