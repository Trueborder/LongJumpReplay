(() => {
  const ICONS = {
    menu: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7h16M4 12h16M4 17h16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="square"/></svg>',
    close: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m6 6 12 12M18 6 6 18" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="square"/></svg>',
    sun: '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="3.5" fill="none" stroke="currentColor" stroke-width="1.7"/><path d="M12 2.5v3M12 18.5v3M2.5 12h3M18.5 12h3M5.3 5.3l2.1 2.1M16.6 16.6l2.1 2.1M18.7 5.3l-2.1 2.1M7.4 16.6l-2.1 2.1" fill="none" stroke="currentColor" stroke-width="1.7"/></svg>',
    moon: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20 15.1A8.2 8.2 0 0 1 8.9 4a8.2 8.2 0 1 0 11.1 11.1Z" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/></svg>',
    x: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m6 6 12 12M18 6 6 18" fill="none" stroke="currentColor" stroke-width="1.8"/></svg>'
  };

  if (!document.querySelector('link[rel="icon"]')) {
    const favicon = document.createElement('link');
    favicon.rel = 'icon';
    favicon.type = 'image/svg+xml';
    favicon.href = '/assets/favicon.svg';
    document.head.append(favicon);
  }

  const cfg = window.SITE_CONFIG || {};
  const product = cfg.products?.longJumpReplay || {};

  /* ---------------------------------------------------------------- cookies
     Theme and language are stored in first-party cookies so the choice follows
     the visitor across pages and survives a return visit.

     Consent model: these are preference cookies, set only after the visitor
     accepts. Declining is a real choice - preferences then live in memory for
     the session only and nothing is written. The consent record itself is
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
    document.cookie = `${name}=${encodeURIComponent(value)}; Max-Age=${maxAge}; Path=/; SameSite=Lax${secure}`;
  };
  const deleteCookie = (name) => {
    document.cookie = `${name}=; Max-Age=0; Path=/; SameSite=Lax`;
  };

  let consent = readCookie(CONSENT_COOKIE);           // 'accepted' | 'declined' | null
  const memoryPrefs = {};

  const readPref = (name) => {
    if (consent === 'accepted') {
      const value = readCookie(name);
      if (value !== null) return value;
    }
    if (name in memoryPrefs) return memoryPrefs[name];
    // A declined preference must remain session-only. Do not fall back to
    // browser storage: it would silently persist an optional preference after
    // the visitor has declined it.
    return null;
  };
  const writePref = (name, value) => {
    memoryPrefs[name] = value;
    if (consent !== 'accepted') return;
    writeCookie(name, value, PREF_MAX_AGE);
  };
  const forgetPrefs = () => {
    ['site-theme', 'site-language'].forEach((name) => {
      deleteCookie(name);
    });
  };

  const storedLanguage = readPref('site-language');
  let lang = storedLanguage === 'cs' ? 'cs' : 'en';

  document.querySelectorAll('.site-footer').forEach((footer) => {
    const github = cfg.developer?.github;
    if (!github || footer.querySelector('[data-github-link]')) return;
    const link = document.createElement('a');
    link.href = github;
    link.target = '_blank';
    link.rel = 'me noopener noreferrer';
    link.dataset.githubLink = '';
    link.textContent = 'GitHub ↗';
    link.setAttribute('aria-label', 'GitHub profile');
    footer.append(link);
  });

  const ui = {
    en: {
      skip: 'Skip to content', software: 'Software', downloads: 'Downloads', about: 'About', contact: 'Contact', account: 'Account',
      theme: 'Switch theme', menu: 'Open menu', close: 'Close menu', language: 'Switch to Czech', closeImage: 'Close image',
      footer: 'Independent software development from the Czech Republic.', cookies: 'Cookie settings'
    },
    cs: {
      skip: 'Přejít na obsah', software: 'Software', downloads: 'Stažení', about: 'O mně', contact: 'Kontakt', account: 'Účet',
      theme: 'Přepnout motiv', menu: 'Otevřít menu', close: 'Zavřít menu', language: 'Přepnout do angličtiny', closeImage: 'Zavřít obrázek',
      footer: 'Nezávislý vývoj softwaru z České republiky.', cookies: 'Nastavení cookies'
    }
  };

  document.querySelectorAll('.site-footer').forEach((footer) => {
    if (footer.querySelector('[data-cookie-settings]')) return;
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'cookie-settings-button';
    button.dataset.cookieSettings = '';
    button.dataset.ui = 'cookies';
    button.textContent = 'Cookie settings';
    button.addEventListener('click', () => showConsentBanner(true));
    footer.append(button);
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
    document.querySelectorAll('[data-theme-toggle]').forEach((element) => element.setAttribute('aria-label', ui[lang].theme));
    if (menu) menu.setAttribute('aria-label', document.body.classList.contains('menu-open') ? ui[lang].close : ui[lang].menu);
    document.querySelector('[data-lightbox-close]')?.setAttribute('aria-label', ui[lang].closeImage);
  };

  const setTheme = (theme) => {
    const safeTheme = theme === 'light' ? 'light' : 'dark';
    document.documentElement.dataset.theme = safeTheme;
    writePref('site-theme', safeTheme);
    document.querySelectorAll('[data-theme-toggle]').forEach((element) => {
      element.innerHTML = safeTheme === 'dark' ? ICONS.sun : ICONS.moon;
    });
    document.querySelector('meta[name="theme-color"]')?.setAttribute('content', safeTheme === 'dark' ? '#0b1013' : '#f2f0e9');
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
  document.querySelectorAll('[data-installer-url]').forEach((element) => { element.href = product.installerUrl || '#'; });

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
  document.querySelectorAll('[data-theme-toggle]').forEach((element) => element.addEventListener('click', () => {
    setTheme(document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark');
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
      text: 'This site uses cookies only to remember your theme and language. No analytics or advertising cookies.',
      accept: 'Accept',
      decline: 'Decline',
      more: 'Privacy',
      label: 'Cookie choices'
    },
    cs: {
      text: 'Tento web používá cookies pouze k zapamatování motivu a jazyka. Žádná analytika ani reklama.',
      accept: 'Přijmout',
      decline: 'Odmítnout',
      more: 'Soukromí',
      label: 'Volby cookies'
    }
  };

  const showConsentBanner = (force = false) => {
    if (!force && (consent === 'accepted' || consent === 'declined')) return;
    document.querySelector('.cookie-banner')?.remove();
    const copy = CONSENT_COPY[lang] || CONSENT_COPY.en;

    const banner = document.createElement('section');
    banner.className = 'cookie-banner';
    banner.setAttribute('role', 'region');
    banner.setAttribute('aria-label', copy.label);

    const text = document.createElement('p');
    text.textContent = copy.text + ' ';
    const more = document.createElement('a');
    more.href = 'https://tomaspisar.cz/privacy/';
    more.className = 'text-link';
    more.textContent = copy.more + ' →';
    text.append(more);

    const actions = document.createElement('div');
    actions.className = 'cookie-actions';

    const decide = (choice) => {
      consent = choice;
      writeCookie(CONSENT_COOKIE, choice, CONSENT_MAX_AGE);
      if (choice === 'accepted') {
        // Persist whatever the visitor already chose this session.
        writePref('site-theme', document.documentElement.dataset.theme || 'dark');
        writePref('site-language', lang);
      } else {
        forgetPrefs();
      }
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
    if (force) decline.focus();
  };

  setTheme(readPref('site-theme') || 'dark');
  renderLanguage();
  showConsentBanner();
})();
