const { chromium } = require('playwright');

const TARGET_URL = 'http://localhost:5173';

(async () => {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1920, height: 1080 } });
  const page = await context.newPage();

  const allErrors = [];

  // Login
  await page.goto(TARGET_URL + '/login', { waitUntil: 'networkidle', timeout: 15000 });
  await page.waitForTimeout(500);
  await page.locator('input[placeholder="用户名"]').first().fill('loli');
  await page.locator('input[placeholder="密码"]').first().fill('llh282');
  await page.locator('button[type="submit"]').filter({ hasText: '登录' }).first().click();
  await page.waitForTimeout(3000);

  console.log('Login result:', page.url().replace(TARGET_URL, ''));

  // Test each page
  const results = [];
  for (const path of ['/overview', '/accounts', '/platforms', '/temp-mail', '/token-tool', '/refresh-log', '/pool-admin', '/audit', '/api', '/settings']) {
    const pageErrors = [];
    page.on('response', r => {
      if (r.status() >= 400) pageErrors.push(`${r.status()} ${r.url()}`);
    });

    try {
      await page.goto(TARGET_URL + path, { waitUntil: 'domcontentloaded', timeout: 10000 });
      await page.waitForTimeout(1500);
    } catch(e) {
      pageErrors.push('NAV_FAIL: ' + e.message);
    }

    const aside = page.locator('aside');
    const box = await aside.count() > 0 ? await aside.first().boundingBox() : null;

    results.push({
      path,
      sidebar: box ? Math.round(box.width) : null,
      ok: pageErrors.length === 0,
      errors: pageErrors
    });
  }

  console.log('\n=== RESULTS ===');
  for (const r of results) {
    const icon = r.ok ? '✅' : '❌';
    const sw = r.sidebar ? `${r.sidebar}px` : 'N/A';
    console.log(`${icon} ${r.path.padEnd(14)} | sidebar: ${sw} | ${r.errors.length ? r.errors.join('; ') : 'OK'}`);
  }

  const allOk = results.every(r => r.ok);
  const sidebarOk = results.filter(r => r.sidebar).every(r => r.sidebar === 180);
  console.log(`\n🎯 All pages OK: ${allOk ? 'YES' : 'NO'} | Sidebar 180px: ${sidebarOk ? 'YES' : 'NO'}`);

  // Take screenshot
  await page.goto(TARGET_URL + '/overview', { waitUntil: 'networkidle', timeout: 10000 });
  await page.screenshot({ path: '/tmp/hx-final.png', fullPage: true });

  await browser.close();
})();
