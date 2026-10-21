/* Shared Pantheon appearance preference. Runs before CSS; no account data. */
(() => {
  'use strict';
  const root = document.documentElement;
  const host = location.hostname;
  const pantheonHost = host === 'pantheon.tomaspisar.cz' || host.endsWith('.pantheon.tomaspisar.cz');
  if (!pantheonHost && !root.hasAttribute('data-pantheon-brand')) return;
  root.setAttribute('data-pantheon-brand', '');
  const key = 'pantheon-theme';
  const valid = value => ['light', 'dark', 'system'].includes(value);
  const media = window.matchMedia('(prefers-color-scheme: dark)');
  const saved = () => {
    let readable = false;
    try {
      readable = true;
      const cookie = document.cookie.split(';').map(v => v.trim()).find(v => v.startsWith(key + '='))?.slice(key.length + 1);
      if (valid(cookie)) return cookie;
    } catch { readable = false; /* restricted cookies: use local preference */ }
    try { const value = localStorage.getItem(key); readable = true; if (valid(value)) return value; } catch { /* private storage */ }
    return readable ? 'system' : null;
  };
  let preference = saved() || 'system';
  const apply = () => {
    const effective = preference === 'system' ? (media.matches ? 'dark' : 'light') : preference;
    root.dataset.pantheonTheme = effective;
    root.dataset.pantheonPreference = preference;
    // Existing shared components use data-theme; only Pantheon is opted in.
    root.dataset.theme = effective;
    const meta = document.querySelector?.('meta[name="theme-color"]');
    if (meta) meta.content = effective === 'dark' ? '#171b17' : '#eeecea';
    updateControls();
  };
  function updateControls() {
    const cs = root.lang === 'cs';
    document.querySelectorAll('[data-pt-theme]').forEach(select => {
      select.value = preference;
      select.setAttribute('aria-label', cs ? 'Barevný motiv' : 'Color theme');
      for (const option of select.options) option.textContent = ({light:cs?'Světlý':'Light',dark:cs?'Tmavý':'Dark',system:cs?'Systém':'System'})[option.value] || option.textContent;
    });
    document.querySelectorAll('[data-pt-theme-label]').forEach(label => { label.textContent = cs ? 'Motiv' : 'Theme'; });
  }
  function choose(value) {
    if (!valid(value)) return;
    preference = value;
    try { localStorage.setItem(key, value); } catch { /* cookies can still persist */ }
    const domain = pantheonHost ? '; Domain=pantheon.tomaspisar.cz' : '';
    try { document.cookie = `${key}=${value}; Path=/; Max-Age=31536000; SameSite=Lax${domain}${location.protocol === 'https:' ? '; Secure' : ''}`; } catch { /* the current page still changes */ }
    apply();
  }
  // Event delegation also covers controls moved into the portal's mobile drawer.
  document.addEventListener('change', event => {
    if (event.target?.matches?.('[data-pt-theme]')) choose(event.target.value);
  });
  const resync = () => { preference = saved() || preference; apply(); };
  media.addEventListener('change', () => { if (preference === 'system') apply(); });
  window.addEventListener('pageshow', resync);
  window.addEventListener('focus', resync);
  window.addEventListener('storage', event => { if (event.key === key) resync(); });
  document.addEventListener('visibilitychange', () => { if (!document.hidden) resync(); });
  document.addEventListener('DOMContentLoaded', updateControls, {once:true});
  new MutationObserver(updateControls).observe(root, {attributes:true,attributeFilter:['lang']});
  apply();
})();
