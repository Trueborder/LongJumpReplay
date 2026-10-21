const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const root = path.join(__dirname, '..', 'tomaspisar.cz', 'account', 'economysuite');
const html = fs.readFileSync(path.join(root, 'index.html'), 'utf8');
const script = fs.readFileSync(path.join(root, 'app.js'), 'utf8');
const css = fs.readFileSync(path.join(root, 'app.css'), 'utf8');
const pantheonCss = fs.readFileSync(path.join(root, 'pantheon.css'), 'utf8');

test('EconomySuite portal exposes live server state and full data refresh', () => {
  assert.match(html, /class="es-live-actions"[^>]*data-state="connecting"[^>]*role="group"/);
  assert.match(html, /id="connection"[^>]*data-state="connecting"/);
  assert.match(html, /<button id="refresh-data" class="es-refresh es-connection-control"/);
  assert.doesNotMatch(html, /<button id="refresh-data"[^>]*hidden/);
  assert.match(script, /server_status/);
  assert.match(script, /closest\('\.es-live-actions'\)\.dataset\.state = state/);
  assert.match(script, /const state = refreshing \? 'connecting'/);
  assert.match(script, /refresh\.dataset\.tooltip = tooltip/);
  assert.match(script, /\/api\/economysuite\/refresh/);
  assert.match(script, /Data refreshed from the server/);
  assert.match(css, /\.es-connection\[data-state=connected\]/);
  assert.match(css, /\.es-connection\[data-state=connecting\]/);
  assert.match(css, /\.es-connection\[data-state=disconnected\]/);
  assert.match(css, /\.es-connection-control:hover::after/);
  assert.doesNotMatch(html, /es-refresh-icon/);
  assert.match(css, /\.es-refresh\[aria-busy=true\]::before\{display:none!important\}/);
  assert.match(css, /body\.es-portal\{padding-top:0\}/);
  assert.match(css, /@keyframes es-connection-pulse/);
});

test('mobile navigation uses an accessible drawer instead of clipped scrolling tabs', () => {
  assert.match(html, /id="menu-toggle"[^>]*aria-controls="navigation-dialog"[^>]*aria-expanded="false"/);
  assert.match(html, /<dialog id="navigation-dialog"[^>]*aria-labelledby="navigation-title"/);
  assert.match(script, /navigationDialog\.showModal\(\)/);
  assert.match(script, /mobileNavigation\.addEventListener\('change', positionNavigation\)/);
  assert.match(script, /mobile-navigation-content'\)\.append\(sidebar\)/);
  assert.match(css, /\.es-nav-dialog #navigation\{flex-direction:column/);
  assert.match(css, /\.es-nav-dialog #navigation a\{min-height:48px/);
});

test('EconomySuite action notifications are toasts and refresh waits for its acknowledgment', () => {
  assert.doesNotMatch(html, /id="status"/);
  assert.doesNotMatch(script, /feedback\?\.inline/);
  assert.match(script, /feedback\?\.toast\[kind\]/);
  assert.match(script, /latest\.refresh_operation\?\.id === refreshOperation/);
  assert.match(script, /latest\.refresh_operation\.state === 'complete'/);
  assert.doesNotMatch(script, /Refresh queued\./);
  assert.match(css, /\.es-portal \.toast:not\(\.is-leaving\)\{opacity:1;transform:none\}/);
});

test('compact sticky header keeps account and logout while secondary controls live in navigation', () => {
  const header = html.match(/<header class="es-header">([\s\S]*?)<\/header>/)[1];
  const sidebar = html.match(/<aside class="es-sidebar">([\s\S]*?)<\/aside>/)[1];
  assert.match(header, /id="logout"/);
  assert.match(header, /id="account-link"[^>]*href="\/economysuite\/settings"[^>]*aria-label=/);
  assert.doesNotMatch(header, /id="language"|es-product-switch/);
  assert.match(sidebar, /es-menu-utilities/);
  assert.match(sidebar, /id="language"/);
  assert.match(html, /class="es-product-switch" href="https:\/\/ljr\.tomaspisar\.cz\/dashboard\/overview"/);
  assert.match(css, /\.es-header\{position:sticky;top:0;z-index:100;height:64px/);
  assert.match(css, /\.es-header\{height:60px;min-height:60px/);
  assert.match(css, /\.es-menu-utilities\{[^}]*margin-top:auto/);
  assert.match(css, /\.es-header-brand\{width:auto;flex:1/);
  assert.match(html, /class="es-brand-text pt-brand">PANTHEON<small data-pt-account-subtitle>/);
  assert.match(html, /src="\/pantheon\/temple\.svg"/);
  assert.match(html, /data-pantheon-brand/);
  assert.match(html, /<script src="\/pantheon\/theme\.js\?v=[\w-]+"><\/script>/);
  assert.match(html, /href="\/pantheon\/design\.css\?v=[\w-]+"/);
  assert.match(html, /href="\/economysuite\/pantheon\.css\?v=[\w-]+"/);
  assert.match(html, /data-pt-site="server"/);
  assert.match(html, /data-pt-site="wiki"/);
  assert.match(html, /data-pt-site="account" aria-current="page"/);
  assert.equal((html.match(/data-pt-theme(?=\s|>)/g) || []).length, 2);
  assert.match(script, /\[data-pt-account-subtitle\]/);
  assert.match(pantheonCss, /--es-paper:var\(--pt-paper\)/);
});

test('purchase return renders instructions and Minecraft currency icons', () => {
  assert.match(script, /Thank you for your purchase/);
  assert.match(script, /Check your balance with \/money or \/tokens/);
  assert.match(script, /es-amethyst/);
  assert.match(script, /es-sunflower/);
  assert.match(script, /es-order-item/);
  assert.match(script, /icon\('store'\)/);
  assert.match(script, /icon\(key\)/);
});

test('store explains how purchases support the developer', () => {
  assert.match(script, /es-store-note/);
  assert.match(script, /Novaryn Solutions/);
  assert.match(script, /Your purchase supports EconomySuite development and operation/);
  assert.match(css, /\.es-store-note/);
});

test('appearance combines current cosmetics without retired titles', () => {
  assert.match(script, /cosmetic-combined-form/);
  assert.match(script, /combined-appearance-preview/);
  assert.match(script, /combinedPreview\(cosmetics\)/);
  assert.match(css, /\.es-combined-preview/);
});

test('level progress exposes current progress and the next level', () => {
  assert.match(script, /function levelProgress/);
  assert.match(script, /aria-valuemax/);
  assert.match(script, /active progress/);
  assert.match(css, /\.es-level-progress/);
});

test('overview explains XP sources and renders synced current and job tasks', () => {
  assert.match(script, /function xpSources/);
  assert.match(script, /Ways to earn XP/);
  assert.match(script, /function currentTasks/);
  assert.match(script, /function jobTask/);
  assert.match(script, /snapshot\.job_task/);
  assert.match(script, /role="progressbar"/);
  assert.match(css, /\.es-xp-sources/);
  assert.match(css, /\.es-job-task/);
});

test('EconomySuite pairing has an explicit four-step onboarding flow', () => {
  assert.match(script, /function onboardingGuide/);
  assert.match(script, /Run \/web link/);
  assert.match(script, /Confirm your player/);
  assert.match(script, /Finish in Minecraft/);
  assert.match(script, /copy-pair-command/);
  assert.match(script, /es-pair-confirmation/);
  assert.match(css, /\.es-onboarding-steps/);
  assert.match(css, /\.es-onboarding-step\.is-active/);
});

test('EconomySuite motion uses purposeful GPU-friendly transitions and reduced motion', () => {
  assert.match(css, /--ease-out:cubic-bezier\(\.23,1,\.32,1\)/);
  assert.match(css, /transform:translateY\(-1px\)/);
  assert.match(css, /transform-origin:left center/);
  assert.match(css, /prefers-reduced-motion:reduce/);
  assert.doesNotMatch(css, /transition:all/);
});

test('store opens purchase agreements in a modal after Order', () => {
  assert.match(script, /id="purchase-dialog" class="es-modal"/);
  assert.match(script, /openPurchaseDialog/);
  assert.match(script, /Confirm and continue to checkout/);
  assert.match(script, /id="accept-purchase-terms" type="checkbox" required/);
  assert.match(script, /id="request-immediate-delivery" type="checkbox" required/);
  assert.doesNotMatch(script, /purchase-consent-form.*?support-note/s);
  assert.match(css, /\.es-modal-card/);
  assert.match(css, /\.es-main\{animation:es-fade-in/);
});

test('purchase history defaults to paid and supports status filters', () => {
  assert.match(script, /purchaseFilter = 'paid'/);
  assert.match(script, /id="purchase-filter"/);
  for (const state of ['all', 'cancelled', 'refunded', 'partially_refunded', 'disputed']) assert.match(script, new RegExp("'" + state + "'"));
});
