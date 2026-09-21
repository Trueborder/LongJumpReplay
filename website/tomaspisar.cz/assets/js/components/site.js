(() => {
  const ICONS = {
    menu: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7h16M4 12h16M4 17h16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="square"/></svg>',
    close: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m6 6 12 12M18 6 6 18" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="square"/></svg>',
    x: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m6 6 12 12M18 6 6 18" fill="none" stroke="currentColor" stroke-width="1.8"/></svg>'
  };

  /* Shared feedback primitives. Keep these deliberately small: the site's
     evidence-desk language already supplies the visual identity, while this
     layer supplies one predictable interaction model for every page. */
  const feedback = (() => {
    const icons = { success: '✓', error: '!', warning: '△', info: 'i' };
    const language = () => document.documentElement.lang === 'cs' ? 'cs' : 'en';
    const titles = { en: { success: 'Done', error: 'Could not complete', warning: 'Check this', info: 'Notice' }, cs: { success: 'Hotovo', error: 'Akci se nepodařilo dokončit', warning: 'Zkontrolujte to', info: 'Oznámení' } };
    const liveRegion = () => {
      let region = document.querySelector('[data-toast-region]');
      if (region) return region;
      region = document.createElement('div');
      region.className = 'toast-region';
      region.dataset.toastRegion = '';
      region.setAttribute('aria-label', language() === 'cs' ? 'Oznámení' : 'Notifications');
      document.body.append(region);
      return region;
    };
    const removeToast = (toast) => {
      if (!toast?.isConnected) return;
      toast.classList.add('is-leaving');
      window.setTimeout(() => toast.remove(), 180);
    };
    const showToast = (kind, message, options = {}) => {
      if (!message) return null;
      const region = liveRegion();
      const duplicate = [...region.children].find((item) => item.dataset.kind === kind && item.querySelector('.toast-message')?.textContent === String(message));
      if (duplicate) return duplicate;
      const toast = document.createElement('div');
      const title = options.title || titles[language()][kind] || titles[language()].info;
      const closeLabel = language() === 'cs' ? 'Zavřít oznámení' : 'Close notification';
      toast.className = `toast toast-${kind}`;
      toast.dataset.kind = kind;
      toast.setAttribute('role', kind === 'error' || kind === 'warning' ? 'alert' : 'status');
      toast.setAttribute('aria-live', kind === 'error' || kind === 'warning' ? 'assertive' : 'polite');
      toast.setAttribute('aria-atomic', 'true');
      toast.innerHTML = `<span class="toast-icon" aria-hidden="true">${icons[kind] || icons.info}</span><span class="toast-copy"><strong class="toast-title"></strong><span class="toast-message"></span></span><button class="toast-close" type="button">${ICONS.x}</button>`;
      toast.querySelector('.toast-close').setAttribute('aria-label', closeLabel);
      toast.querySelector('.toast-title').textContent = title;
      toast.querySelector('.toast-message').textContent = message;
      toast.querySelector('.toast-close').addEventListener('click', () => removeToast(toast));
      region.append(toast);
      window.requestAnimationFrame(() => toast.classList.add('is-visible'));
      const duration = options.duration ?? (kind === 'error' ? 8500 : kind === 'warning' ? 6500 : 4800);
      if (duration > 0) toast._dismissTimer = window.setTimeout(() => removeToast(toast), duration);
      return toast;
    };
    const setInline = (target, message, kind = 'info') => {
      const element = typeof target === 'string' ? document.querySelector(target) : target;
      if (!element) return;
      element.textContent = message || '';
      element.dataset.state = message ? kind : '';
      element.hidden = !message;
      element.setAttribute('aria-live', kind === 'error' || kind === 'warning' ? 'assertive' : 'polite');
      element.setAttribute('role', kind === 'error' || kind === 'warning' ? 'alert' : 'status');
    };
    const bindDialog = (dialog) => {
      if (!dialog || dialog.dataset.feedbackBound === 'true') return dialog;
      dialog.dataset.feedbackBound = 'true';
      let previousFocus = null;
      dialog.addEventListener('beforetoggle', (event) => { if (event.newState === 'open') previousFocus = document.activeElement; });
      dialog.addEventListener('close', () => {
        const focusTarget = previousFocus;
        previousFocus = null;
        if (focusTarget?.isConnected && typeof focusTarget.focus === 'function') window.setTimeout(() => focusTarget.focus(), 0);
      });
      return dialog;
    };
    const confirm = ({ title, description, confirmLabel = 'Confirm', cancelLabel = 'Cancel', destructive = false } = {}) => new Promise((resolve) => {
      const dialog = document.createElement('dialog');
      dialog.className = `feedback-modal${destructive ? ' feedback-modal-danger' : ''}`;
      dialog.setAttribute('aria-labelledby', 'feedback-modal-title');
      dialog.setAttribute('aria-describedby', 'feedback-modal-description');
      dialog.setAttribute('aria-modal', 'true');
      dialog.innerHTML = `<div class="feedback-modal-kicker">LONGJUMPREPLAY / CONFIRMATION</div><h2 id="feedback-modal-title"></h2><p id="feedback-modal-description"></p><div class="feedback-modal-actions"><button type="button" class="button button-outline" data-modal-cancel></button><button type="button" class="button ${destructive ? 'button-danger' : 'button-primary'}" data-modal-confirm></button></div>`;
      dialog.querySelector('#feedback-modal-title').textContent = title || '';
      dialog.querySelector('#feedback-modal-description').textContent = description || '';
      dialog.querySelector('[data-modal-cancel]').textContent = cancelLabel;
      dialog.querySelector('[data-modal-confirm]').textContent = confirmLabel;
      document.body.append(dialog);
      bindDialog(dialog);
      const restoreFocus = document.activeElement;
      let settled = false;
      const finish = (value) => {
        if (settled) return;
        settled = true;
        if (dialog.open) dialog.close();
        else dialog.remove();
        resolve(value);
      };
      dialog.querySelector('[data-modal-cancel]').addEventListener('click', () => finish(false));
      dialog.querySelector('[data-modal-confirm]').addEventListener('click', () => finish(true));
      dialog.addEventListener('cancel', (event) => { event.preventDefault(); finish(false); });
      dialog.addEventListener('click', (event) => { if (event.target === dialog) finish(false); });
      dialog.addEventListener('close', () => {
        dialog.remove();
        if (restoreFocus?.isConnected && typeof restoreFocus.focus === 'function') window.setTimeout(() => restoreFocus.focus(), 0);
      }, { once: true });
      if (typeof dialog.showModal === 'function') dialog.showModal();
      else dialog.setAttribute('open', '');
      dialog.querySelector('[data-modal-cancel]').focus();
    });
    document.querySelectorAll('dialog').forEach(bindDialog);
    new MutationObserver((records) => records.forEach((record) => record.addedNodes.forEach((node) => {
      if (node.nodeType === 1) {
        if (node.matches?.('dialog')) bindDialog(node);
        node.querySelectorAll?.('dialog').forEach(bindDialog);
      }
    }))).observe(document.documentElement, { childList: true, subtree: true });
    return { toast: { success: (message, options) => showToast('success', message, options), error: (message, options) => showToast('error', message, options), warning: (message, options) => showToast('warning', message, options), info: (message, options) => showToast('info', message, options) }, inline: setInline, bindDialog, confirm };
  })();
  window.LJR_FEEDBACK = feedback;

  if (!document.querySelector('link[rel="icon"]')) {
    const favicon = document.createElement('link');
    favicon.rel = 'icon';
    favicon.type = 'image/svg+xml';
    favicon.href = '/assets/icons/favicon.svg';
    document.head.append(favicon);
  }

  const cfg = window.SITE_CONFIG || {};
  const product = cfg.products?.longJumpReplay || {};

  // LongJumpReplay has a small set of product-level pages, so keep their
  // navigation contextual without duplicating the global site header.
  const renderProductContext = () => {
    const pathname = window.location.pathname.replace(/\/?$/, '/');
    const context = pathname.startsWith('/products/long-jump-replay/')
      ? {
          name: 'LongJumpReplay',
          route: '/products/long-jump-replay/',
          links: [
            { en: 'Overview', cs: 'Přehled', href: '/products/long-jump-replay/' },
            { en: 'Downloads', cs: 'Stažení', href: '/products/long-jump-replay/download/' },
            { en: 'Licensing', cs: 'Licence', href: '/products/long-jump-replay/licensing/' },
            { en: 'Privacy', cs: 'Soukromí', href: '/products/long-jump-replay/privacy/' }
          ]
        }
      : null;
    const header = document.querySelector('.site-header');
    if (!context || !header || document.querySelector('[data-product-context]')) return;

    const nav = document.createElement('nav');
    nav.className = 'product-context-nav';
    nav.dataset.productContext = '';
    nav.setAttribute('aria-label', `${context.name} product navigation`);

    const productLink = document.createElement('a');
    productLink.className = 'product-context-brand';
    productLink.href = context.route;
    productLink.innerHTML = '<span class="product-context-kicker" data-en="PRODUCT" data-cs="PRODUKT">PRODUCT</span><strong>LongJumpReplay</strong>';
    nav.append(productLink);

    const links = document.createElement('div');
    links.className = 'product-context-links';
     context.links.forEach(({ en, cs, href }) => {
       const link = document.createElement('a');
       link.href = href;
       link.dataset.en = en;
       link.dataset.cs = cs;
       link.textContent = en;
       if (pathname === href) link.setAttribute('aria-current', 'page');
       links.append(link);
     });
     nav.append(links);

     header.insertAdjacentElement('afterend', nav);
   };
  renderProductContext();

  // The readiness page is deliberately informational: it helps an operator
  // size a station before an event without pretending to probe the computer
  // from the public website. The desktop app remains authoritative at runtime.
  if (location.pathname === '/products/long-jump-replay/' && !document.querySelector('[data-ljr-readiness]')) {
    const requirements = document.querySelector('.requirements-list')?.closest('.content-section');
    if (requirements) {
      const section = document.createElement('section');
      section.className = 'section-shell content-section';
      section.dataset.ljrReadiness = '';
      section.innerHTML = `
        <div class="section-heading-row"><div><p class="eyebrow" data-en="PRE-EVENT READINESS" data-cs="PŘÍPRAVA PŘED ZÁVODEM">PRE-EVENT READINESS</p><h2 data-en="Choose the station for the job." data-cs="Zvolte stanici podle úkolu.">Choose the station for the job.</h2></div><p class="heading-note" data-en="The camera, USB path, storage, and analysis workload all matter. These tiers are planning guidance; verify the complete setup in LongJumpReplay before competition." data-cs="Záleží na kameře, USB připojení, úložišti i zátěži analýzy. Tato úrovně slouží pro plánování; před závodem ověřte celou sestavu v LongJumpReplay.">The camera, USB path, storage, and analysis workload all matter. These tiers are planning guidance; verify the complete setup in LongJumpReplay before competition.</p></div>
        <div class="hardware-matrix" role="table" aria-label="LongJumpReplay station tiers">
          <article class="hardware-tier" role="row"><div><span class="tag" data-en="MINIMUM" data-cs="MINIMUM">MINIMUM</span><h3 data-en="Review station" data-cs="Kontrolní stanice">Review station</h3><p data-en="For replay and frame-by-frame judging." data-cs="Pro replay a posuzování po snímcích.">For replay and frame-by-frame judging.</p></div><dl><div><dt>CPU</dt><dd>Core i5 / Ryzen 5</dd></div><div><dt>RAM</dt><dd>16 GB</dd></div><div><dt>CAMERA</dt><dd>720p / 60 FPS</dd></div><div><dt>DISK</dt><dd data-en="SSD · 10 GB free" data-cs="SSD · 10 GB volných">SSD · 10 GB free</dd></div></dl></article>
          <article class="hardware-tier hardware-tier-featured" role="row"><div><span class="tag" data-en="BALANCED" data-cs="VYVÁŽENÁ">BALANCED</span><h3 data-en="Competition station" data-cs="Závodní stanice">Competition station</h3><p data-en="The recommended setup for live capture and assist review." data-cs="Doporučená sestava pro živý záznam a asistovanou kontrolu.">The recommended setup for live capture and assist review.</p></div><dl><div><dt>CPU</dt><dd>Core i7 / Ryzen 7</dd></div><div><dt>RAM</dt><dd>32 GB</dd></div><div><dt>CAMERA</dt><dd>720p / 120 FPS</dd></div><div><dt>USB</dt><dd data-en="USB 3 · direct port" data-cs="USB 3 · přímý port">USB 3 · direct port</dd></div></dl></article>
          <article class="hardware-tier" role="row"><div><span class="tag" data-en="HIGH-SPEED" data-cs="VYSOKÁ RYCHLOST">HIGH-SPEED</span><h3 data-en="Analysis station" data-cs="Analytická stanice">Analysis station</h3><p data-en="For longer sessions, high-FPS capture, and heavier analysis." data-cs="Pro delší seance, vysoké FPS a náročnější analýzu.">For longer sessions, high-FPS capture, and heavier analysis.</p></div><dl><div><dt>CPU</dt><dd>Core i7 / Ryzen 7+</dd></div><div><dt>RAM</dt><dd>32 GB+</dd></div><div><dt>CAMERA</dt><dd>1080p / 120 FPS</dd></div><div><dt>DISK</dt><dd data-en="NVMe · 100 GB free" data-cs="NVMe · 100 GB volných">NVMe · 100 GB free</dd></div></dl></article>
        </div>
        <div class="readiness-notes"><article><span class="eyebrow" data-en="STORAGE FORECAST" data-cs="ODHAD ÚLOŽIŠTĚ">STORAGE FORECAST</span><p data-en="Plan for more space when saving long sessions or higher-quality exports. The app reports the live free-disk and recording forecast in its Performance tab." data-cs="Při ukládání delších seancí nebo kvalitnějších exportů počítejte s větší rezervou. Aplikace zobrazuje volné místo a odhad záznamu v záložce Výkon.">Plan for more space when saving long sessions or higher-quality exports. The app reports the live free-disk and recording forecast in its Performance tab.</p></article><article><span class="eyebrow" data-en="CAPTURE-HEALTH GUARD" data-cs="KONTROLA STAVU ZÁZNAMU">CAPTURE-HEALTH GUARD</span><p data-en="Before the event, confirm stable FPS, no dropped frames, a healthy buffer, enough disk space, and a direct USB 3 camera connection." data-cs="Před závodem ověřte stabilní FPS, nulové výpadky snímků, zdravý buffer, dostatek místa a přímé připojení kamery přes USB 3.">Before the event, confirm stable FPS, no dropped frames, a healthy buffer, enough disk space, and a direct USB 3 camera connection.</p></article></div>`;
      requirements.insertAdjacentElement('afterend', section);
    }
  }

  /* ---------------------------------------------------------------- cookies
     Language is stored in a first-party cookie so the choice follows the
     visitor across pages and survives a return visit.

     Consent model: these are preference cookies, set only after the visitor
     accepts. Declining is a real choice - preferences then live in session
     storage only and no preference cookie is written. The consent record itself is
     stored either way, because remembering "no" is what stops the banner
     reappearing on every page, and a site cannot ask for permission to
     remember a refusal.

     No analytics or advertising cookies are used. Stripe's payment component
     may set its own necessary cookies on the purchase page. */
  const CONSENT_COOKIE = 'ljr-consent';
  const CONSENT_MAX_AGE = 60 * 60 * 24 * 180;   // six months, then ask again
  const PREF_MAX_AGE = 60 * 60 * 24 * 365;

  const readCookie = (name) => {
    const match = document.cookie.match(new RegExp('(?:^|; )' + name.replace(/[-.]/g, '\\$&') + '=([^;]*)'));
    return match ? decodeURIComponent(match[1]) : null;
  };
  const writeCookie = (name, value, maxAge) => {
    const secure = location.protocol === 'https:' ? '; Secure' : '';
    const domain = /(^|\.)tomaspisar\.cz$/i.test(location.hostname) ? '; Domain=tomaspisar.cz' : '';
    // Remove an older host-only value before writing the shared main/account value.
    document.cookie = `${name}=; Max-Age=0; Path=/; SameSite=Lax${secure}`;
    document.cookie = `${name}=${encodeURIComponent(value)}; Max-Age=${maxAge}; Path=/; SameSite=Lax${secure}${domain}`;
  };
  const deleteCookie = (name) => {
    document.cookie = `${name}=; Max-Age=0; Path=/; SameSite=Lax`;
    if (/(^|\.)tomaspisar\.cz$/i.test(location.hostname)) {
      document.cookie = `${name}=; Max-Age=0; Path=/; SameSite=Lax; Domain=tomaspisar.cz`;
    }
  };

  let consent = readCookie(CONSENT_COOKIE);           // 'accepted' | 'declined' | null
  if (consent === 'accepted' || consent === 'declined') {
    writeCookie(CONSENT_COOKIE, consent, CONSENT_MAX_AGE);
  }
  const memoryPrefs = {};

  const readSessionPref = (name) => {
    try { return window.sessionStorage.getItem(name); } catch (_) { return null; }
  };
  const writeSessionPref = (name, value) => {
    try { window.sessionStorage.setItem(name, value); } catch (_) { /* memory fallback below */ }
  };

  const readPref = (name) => {
    if (consent === 'accepted') {
      const value = readCookie(name);
      if (value !== null) return value;
    }
    if (name in memoryPrefs) return memoryPrefs[name];
    return readSessionPref(name);
  };
  const writePref = (name, value) => {
    memoryPrefs[name] = value;
    writeSessionPref(name, value);
    if (consent !== 'accepted') return;
    writeCookie(name, value, PREF_MAX_AGE);
  };
  const forgetPrefs = () => {
    deleteCookie('site-language');
  };

  // Theme selection was retired when the website became permanently light.
  deleteCookie('site-theme');
  try { window.sessionStorage.removeItem('site-theme'); } catch (_) { /* unavailable storage */ }

  const storedLanguage = readPref('site-language');
  let lang = storedLanguage === 'cs' ? 'cs' : 'en';

  // Keep older minified product markup accurate while email remains primary.
  document.querySelectorAll('[data-en]').forEach((element) => {
    if (element.dataset.en === 'Activation uses the email address you buy with - there is no license key to keep safe. If you would rather test first, the installer includes a free 72-hour trial.') {
      element.dataset.en = 'Activation is email-first. A reusable alternative key is available in the customer portal. The installer also includes a replay-only 72-hour evaluation.';
      element.dataset.cs = 'Aktivace probíhá primárně e-mailem. Opakovaně použitelný alternativní klíč najdete v zákaznickém portálu. Instalátor obsahuje také 72hodinové testování pouze pro přehrávání.';
    }
  });

  // Keep footer structure consistent even though a few older pages have
  // slightly different link sets. The shell gives the footer a clear identity
  // area, navigation area, and controls area without duplicating HTML in every
  // page template.
  const footerShell = (footer) => {
    let shell = footer.querySelector('[data-footer-shell]');
    if (shell) return shell;
    shell = document.createElement('div');
    shell.className = 'site-footer-shell';
    shell.dataset.footerShell = '';
    const identity = document.createElement('div');
    identity.className = 'site-footer-identity';
    const links = document.createElement('nav');
    links.className = 'site-footer-links';
    links.setAttribute('aria-label', 'Footer');
    const children = [...footer.children];
    children.forEach((child, index) => (index < 2 ? identity : links).append(child));
    shell.append(identity, links);
    footer.append(shell);
    return shell;
  };

  let showConsentBanner = () => {};

  document.querySelectorAll('.site-footer').forEach((footer) => {
    const shell = footerShell(footer);
    const links = shell.querySelector('.site-footer-links');
    const github = cfg.developer?.github;
    if (!github || links.querySelector('[data-github-link]')) return;
    const link = document.createElement('a');
    link.href = github;
    link.target = '_blank';
    link.rel = 'me noopener noreferrer';
    link.dataset.githubLink = '';
    link.textContent = 'GitHub ↗';
    link.setAttribute('aria-label', 'GitHub profile');
    links.append(link);
  });

  const ui = {
    en: {
      skip: 'Skip to content', software: 'Software', about: 'About', contact: 'Contact', account: 'Account',
      menu: 'Open menu', close: 'Close menu', language: 'Switch to Czech', closeImage: 'Close image',
      footer: 'Independent software development from the Czech Republic.', cookies: 'Cookie settings'
    },
    cs: {
      skip: 'Přejít na obsah', software: 'Software', about: 'O mně', contact: 'Kontakt', account: 'Účet',
      menu: 'Otevřít menu', close: 'Zavřít menu', language: 'Přepnout do angličtiny', closeImage: 'Zavřít obrázek',
      footer: 'Nezávislý vývoj softwaru z České republiky.', cookies: 'Nastavení cookies'
    }
  };

  document.querySelectorAll('.site-footer').forEach((footer) => {
    const links = footer.querySelector('.site-footer-links') || footerShell(footer).querySelector('.site-footer-links');
    if (links.querySelector('[data-cookie-settings]')) return;
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'cookie-settings-control';
    button.dataset.cookieSettings = '';
    button.dataset.ui = 'cookies';
    button.setAttribute('aria-haspopup', 'dialog');
    button.textContent = 'Cookie settings';
    button.addEventListener('click', () => showConsentBanner(true));
    links.append(button);
  });

  const menu = document.querySelector('[data-menu-toggle]');
  const header = document.querySelector('.site-header');
  const nav = document.querySelector('.main-nav');

  const updateHeaderMaterial = () => {
    header?.classList.toggle('is-scrolled', window.scrollY > 8);
  };

  let headerFrame = 0;
  window.addEventListener('scroll', () => {
    if (headerFrame) return;
    headerFrame = requestAnimationFrame(() => {
      headerFrame = 0;
      updateHeaderMaterial();
    });
  }, { passive: true });
  updateHeaderMaterial();

  const renderLanguage = () => {
    document.documentElement.lang = lang;
    document.querySelectorAll('[data-en], [data-cs]').forEach((element) => {
      const value = element.dataset[lang] || element.dataset.en || element.textContent;
      if (value.includes('<')) element.innerHTML = value;
      else element.textContent = value;
    });
    document.querySelectorAll('[data-ui]').forEach((element) => {
      const value = ui[lang][element.dataset.ui];
      if (value) element.textContent = value;
    });
    document.querySelectorAll('[data-lang-label]').forEach((element) => {
      element.textContent = lang === 'en' ? 'CZ' : 'EN';
      element.setAttribute('aria-label', ui[lang].language);
    });
    if (menu) menu.setAttribute('aria-label', document.body.classList.contains('menu-open') ? ui[lang].close : ui[lang].menu);
    document.querySelector('[data-lightbox-close]')?.setAttribute('aria-label', ui[lang].closeImage);
  };

  const closeMenu = () => {
    document.body.classList.remove('menu-open');
    if (menu) {
      menu.innerHTML = ICONS.menu;
      menu.setAttribute('aria-expanded', 'false');
    }
    renderLanguage();
  };

  if (nav && !nav.id) nav.id = 'primary-navigation';
  nav?.setAttribute('aria-label', nav.getAttribute('aria-label') || 'Primary navigation');
  menu?.setAttribute('aria-controls', nav?.id || 'primary-navigation');
  menu?.setAttribute('aria-expanded', 'false');
  if (menu) menu.innerHTML = ICONS.menu;
  menu?.addEventListener('click', () => {
    const open = document.body.classList.toggle('menu-open');
    menu.innerHTML = open ? ICONS.close : ICONS.menu;
    menu.setAttribute('aria-expanded', String(open));
    renderLanguage();
  });

  document.addEventListener('pointerdown', (event) => {
    if (!document.body.classList.contains('menu-open') || header?.contains(event.target)) return;
    closeMenu();
  });

  const path = window.location.pathname.toLowerCase();
  document.querySelectorAll('.main-nav a').forEach((link) => {
    const href = link.getAttribute('href') || '';
    const active = href !== '/' && path.startsWith(href.toLowerCase());
    if (active) link.setAttribute('aria-current', 'page');
    link.addEventListener('click', closeMenu);
  });

  document.querySelectorAll('[data-email]').forEach((element) => {
    const email = cfg.developer?.email || '';
    element.textContent = email;
    element.href = `mailto:${email}`;
  });
  document.querySelectorAll('[data-product-version]').forEach((element) => { element.textContent = product.version || '—'; });
  document.querySelectorAll('[data-product-price]').forEach((element) => { element.textContent = product.price || '—'; });
  const installerLinks = [...document.querySelectorAll('[data-installer-url]')];
  installerLinks.forEach((element) => { element.href = product.installerUrl || '#'; });

  let downloadSafetyDialog = document.querySelector('[data-download-safety-dialog]');
  if (installerLinks.length && !downloadSafetyDialog) {
    const template = document.createElement('template');
    template.innerHTML = `
      <dialog class="download-safety-dialog" data-download-safety-dialog aria-labelledby="download-started-title">
        <div class="download-safety-dialog-panel">
          <div class="download-safety-icon" aria-hidden="true">
            <svg viewBox="0 0 24 24" focusable="false"><path d="M12 3 20 6v5c0 5.2-3.4 8.5-8 10-4.6-1.5-8-4.8-8-10V6l8-3Z"/><path d="m8.5 12 2.2 2.2 4.8-5"/></svg>
          </div>
          <div>
            <p class="eyebrow" data-en="DOWNLOAD STARTED" data-cs="STAHOVÁNÍ ZAHÁJENO">DOWNLOAD STARTED</p>
            <h2 id="download-started-title" data-en="Your browser may ask you to confirm the download." data-cs="Prohlížeč vás může požádat o potvrzení stažení.">Your browser may ask you to confirm the download.</h2>
            <p data-en="If LJR_setup.exe does not appear, open your browser's Downloads panel and choose Keep or Download anyway. The official file from files.tomaspisar.cz is safe to proceed with." data-cs="Pokud se soubor LJR_setup.exe nezobrazí, otevřete v prohlížeči panel Stažené soubory a zvolte Ponechat nebo Přesto stáhnout. S oficiálním souborem z files.tomaspisar.cz můžete bezpečně pokračovat.">If LJR_setup.exe does not appear, open your browser's Downloads panel and choose Keep or Download anyway. The official file from files.tomaspisar.cz is safe to proceed with.</p>
            <p class="download-safety-dialog-windows" data-en="When you run the setup, Windows SmartScreen may also ask for confirmation. Choose More info, verify LJR_setup.exe, then choose Run anyway." data-cs="Při spuštění instalace může potvrzení vyžadovat také Windows SmartScreen. Zvolte Další informace, ověřte LJR_setup.exe a poté vyberte Přesto spustit.">When you run the setup, Windows SmartScreen may also ask for confirmation. Choose More info, verify LJR_setup.exe, then choose Run anyway.</p>
            <div class="download-safety-dialog-actions">
              <button class="button button-primary" type="button" data-download-safety-close data-en="Understood" data-cs="Rozumím">Understood</button>
            </div>
          </div>
        </div>
      </dialog>`;
    downloadSafetyDialog = template.content.firstElementChild;
    document.body.append(downloadSafetyDialog);
  }
  const downloadSafetyClose = downloadSafetyDialog?.querySelector('[data-download-safety-close]');
  let downloadSafetyTrigger = null;
  installerLinks.forEach((element) => {
    element.addEventListener('click', () => {
      downloadSafetyTrigger = element;
      // Let the anchor begin the browser download first, then show the safety
      // guidance while the customer checks the Downloads panel.
      window.setTimeout(() => {
        if (!downloadSafetyDialog || downloadSafetyDialog.open) return;
        if (typeof downloadSafetyDialog.showModal === 'function') downloadSafetyDialog.showModal();
        else downloadSafetyDialog.setAttribute('open', '');
        downloadSafetyClose?.focus();
      }, 0);
    });
  });
  downloadSafetyClose?.addEventListener('click', () => downloadSafetyDialog?.close());
  downloadSafetyDialog?.addEventListener('close', () => {
    downloadSafetyTrigger?.focus();
    downloadSafetyTrigger = null;
  });
  downloadSafetyDialog?.addEventListener('click', (event) => {
    if (event.target === downloadSafetyDialog) downloadSafetyDialog.close();
  });

  const applyPublishedRelease = (manifest) => {
    const release = manifest?.schema === 1 ? manifest.payload : null;
    if (!release || release.product !== 'longjumpreplay' || release.channel !== 'stable') return;
    if (!/^\d+\.\d+\.\d+$/.test(release.version || '')) return;
    try {
      const installer = new URL(release.installer_url);
      const expected = `/releases/${release.version}/LongJumpReplay-Setup-${release.version}.exe`;
      if (installer.protocol !== 'https:' || installer.hostname !== 'files.tomaspisar.cz' || installer.pathname !== expected) return;
      document.querySelectorAll('[data-product-version]').forEach((element) => { element.textContent = release.version; });
    } catch (_) {
      // Keep the configured fallback when release metadata is unavailable.
    }
  };

  if (product.releaseManifestUrl) {
    fetch(product.releaseManifestUrl, { cache: 'no-store', mode: 'cors' })
      .then((response) => {
        if (!response.ok) throw new Error(`release manifest ${response.status}`);
        return response.json();
      })
      .then(applyPublishedRelease)
      .catch(() => {});
  }

  // Licensing figures live in one place so a change to the backend's real
  // limits is a single edit in site.config.js. These write textContent, so
  // never put data-en/data-cs on the same element - use a nested element.
  const licensing = cfg.licensing || {};
  document.querySelectorAll('[data-license-devices]').forEach((element) => { element.textContent = licensing.deviceLimit ?? '—'; });
  document.querySelectorAll('[data-license-grace]').forEach((element) => { element.textContent = licensing.offlineGraceDays ?? '—'; });
  document.querySelectorAll('[data-license-updates]').forEach((element) => { element.textContent = licensing.updateMonths ?? '—'; });
  document.querySelectorAll('[data-mail-subject]').forEach((element) => {
    element.href = `mailto:${cfg.developer?.email || ''}?subject=${encodeURIComponent(element.dataset.mailSubject)}`;
  });

  document.querySelectorAll('[data-lang-toggle]').forEach((element) => element.addEventListener('click', () => {
    lang = lang === 'en' ? 'cs' : 'en';
    writePref('site-language', lang);
    renderLanguage();
  }));
  const preview = document.querySelector('.product-image img');
  if (preview && product.screenshots?.[0]) {
    preview.src = product.screenshots[0];
    preview.alt = 'LongJumpReplay main replay interface';
    preview.width = 1280;
    preview.height = 720;
  }

  const gallery = document.querySelector('.screenshot-grid');
  if (gallery && product.screenshots?.length) {
    const labels = [
      { en: 'MAIN SCREEN / LIVE REVIEW', cs: 'HLAVNÍ OBRAZOVKA / ŽIVÁ KONTROLA', alt: 'LongJumpReplay main replay and judging interface' },
      { en: 'RECORDINGS / ATTEMPT HISTORY', cs: 'ZÁZNAMY / HISTORIE POKUSŮ', alt: 'LongJumpReplay recordings list with attempt results' },
      { en: 'COMPETITION BOARD / ATTEMPTS', cs: 'SOUTĚŽNÍ TABULE / POKUSY', alt: 'LongJumpReplay competition board showing athletes and attempts' }
    ];
    const template = gallery.querySelector('figure');
    product.screenshots.forEach((src, index) => {
      if (!template || !labels[index]) return;
      const figure = gallery.children[index] || template.cloneNode(true);
      const image = figure.querySelector('img');
      const caption = figure.querySelector('figcaption');
      image.src = src;
      image.alt = labels[index].alt;
      image.loading = 'lazy';
      image.width = 1280;
      image.height = 720;
      image.dataset.lightbox = '';
      caption.dataset.en = labels[index].en;
      caption.dataset.cs = labels[index].cs;
      caption.textContent = labels[index][lang];
      if (!figure.parentElement) gallery.appendChild(figure);
    });
  }

  const revealTargets = document.querySelectorAll('.page-hero, .content-section');
  const reducedMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
  if (revealTargets.length && !reducedMotion && 'IntersectionObserver' in window) {
    document.documentElement.classList.add('motion-ready');
    revealTargets.forEach((element, index) => {
      element.classList.add('reveal');
      element.style.setProperty('--reveal-delay', `${Math.min(index * 35, 140)}ms`);
    });
    const revealObserver = new IntersectionObserver((entries, observer) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        entry.target.classList.add('is-visible');
        observer.unobserve(entry.target);
      });
    }, { rootMargin: '0px 0px -10% 0px', threshold: .06 });
    revealTargets.forEach((element) => revealObserver.observe(element));
  }

  const dialog = document.querySelector('[data-lightbox-dialog]');
  const dialogImage = dialog?.querySelector('img');
  const closeButton = document.querySelector('[data-lightbox-close]');
  let lightboxTrigger = null;
  if (closeButton) closeButton.innerHTML = ICONS.x;
  const openLightbox = (image) => {
    if (!dialog || !dialogImage) return;
    lightboxTrigger = image;
    dialogImage.src = image.src;
    dialogImage.alt = image.alt;
    dialog.showModal();
    closeButton?.focus();
  };
  document.querySelectorAll('[data-lightbox]').forEach((image) => {
    image.tabIndex = 0;
    image.setAttribute('role', 'button');
    image.setAttribute('aria-label', `Open image: ${image.alt}`);
    image.addEventListener('click', () => openLightbox(image));
    image.addEventListener('keydown', (event) => {
      if (event.key !== 'Enter' && event.key !== ' ') return;
      event.preventDefault();
      openLightbox(image);
    });
  });
  closeButton?.addEventListener('click', () => dialog?.close());
  dialog?.addEventListener('close', () => {
    lightboxTrigger?.focus();
    lightboxTrigger = null;
  });
  dialog?.addEventListener('click', (event) => {
    if (event.target === dialog) dialog.close();
  });

  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') closeMenu();
  });

  /* ------------------------------------------------------- consent banner
     Built in JS rather than duplicated into eight hand-maintained HTML files.
     It is added after the main content so it does not steal the first tab
     stop, and it never blocks the page: nothing non-essential is stored until
     a choice is made, so there is no reason to hold the visitor hostage. */
  const CONSENT_COPY = {
    en: {
      text: 'This site uses cookies only to remember your language. No analytics or advertising cookies.',
      accept: 'Accept',
      decline: 'Decline',
      more: 'Privacy',
      label: 'Cookie choices'
    },
    cs: {
      text: 'Tento web používá cookies pouze k zapamatování jazyka. Žádná analytika ani reklama.',
      accept: 'Přijmout',
      decline: 'Odmítnout',
      more: 'Soukromí',
      label: 'Volby cookies'
    }
  };

  showConsentBanner = (force = false) => {
    if (!force && (consent === 'accepted' || consent === 'declined')) return;
    document.querySelector('.consent-dialog')?.remove();
    const copy = CONSENT_COPY[lang] || CONSENT_COPY.en;

    const banner = document.createElement('dialog');
    banner.className = 'consent-dialog';
    banner.setAttribute('role', 'dialog');
    banner.setAttribute('aria-modal', 'true');
    banner.setAttribute('aria-label', copy.label);

    const text = document.createElement('p');
    text.textContent = copy.text + ' ';
    const more = document.createElement('a');
    more.href = 'https://tomaspisar.cz/legal/privacy/';
    more.className = 'text-link';
    more.textContent = copy.more + ' →';
    text.append(more);

    const actions = document.createElement('div');
    actions.className = 'consent-actions';

    const decide = (choice) => {
      consent = choice;
      writeCookie(CONSENT_COOKIE, choice, CONSENT_MAX_AGE);
      if (choice === 'accepted') {
        // Persist whatever the visitor already chose this session.
        writePref('site-language', lang);
      } else {
        forgetPrefs();
      }
      if (banner.open && typeof banner.close === 'function') banner.close();
      banner.remove();
    };

    const decline = document.createElement('button');
    decline.type = 'button';
    decline.className = 'button button-outline';
    decline.textContent = copy.decline;
    decline.addEventListener('click', () => decide('declined'));

    const accept = document.createElement('button');
    accept.type = 'button';
    accept.className = 'button button-primary';
    accept.textContent = copy.accept;
    accept.addEventListener('click', () => decide('accepted'));

    actions.append(decline, accept);
    banner.append(text, actions);
    document.body.append(banner);
    if (force && typeof banner.showModal === 'function') banner.showModal();
    else banner.setAttribute('open', '');
    if (force) decline.focus();
  };

  renderLanguage();
  showConsentBanner();
})();
