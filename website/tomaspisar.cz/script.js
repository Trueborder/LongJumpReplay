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
  const storedLanguage = localStorage.getItem('site-language');
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
      skip: 'Skip to content', software: 'Software', downloads: 'Downloads', about: 'About', contact: 'Contact',
      theme: 'Switch theme', menu: 'Open menu', close: 'Close menu', language: 'Switch to Czech', closeImage: 'Close image',
      footer: 'Independent software development from the Czech Republic.'
    },
    cs: {
      skip: 'Přejít na obsah', software: 'Software', downloads: 'Stažení', about: 'O mně', contact: 'Kontakt',
      theme: 'Přepnout motiv', menu: 'Otevřít menu', close: 'Zavřít menu', language: 'Přepnout do angličtiny', closeImage: 'Zavřít obrázek',
      footer: 'Nezávislý vývoj softwaru z České republiky.'
    }
  };

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
    localStorage.setItem('site-theme', safeTheme);
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
  document.querySelectorAll('[data-mail-subject]').forEach((element) => {
    element.href = `mailto:${cfg.developer?.email || ''}?subject=${encodeURIComponent(element.dataset.mailSubject)}`;
  });

  document.querySelectorAll('[data-lang-toggle]').forEach((element) => element.addEventListener('click', () => {
    lang = lang === 'en' ? 'cs' : 'en';
    localStorage.setItem('site-language', lang);
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

  setTheme(localStorage.getItem('site-theme') || 'dark');
  renderLanguage();
})();
