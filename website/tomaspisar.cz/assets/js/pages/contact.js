(() => {
  const form = document.querySelector('[data-contact-form]');
  if (!form) return;

  const config = window.SITE_CONFIG?.contact || {};
  const status = document.querySelector('[data-contact-status]');
  const submit = form.querySelector('button[type="submit"]');
  const widgetHost = form.querySelector('[data-contact-turnstile]');
  let turnstileId = null;
  let token = '';

  const copy = (en, cs) => document.documentElement.lang === 'cs' ? cs : en;
  const setStatus = (message, kind = '') => {
    if (!status) return;
    status.textContent = message;
    status.dataset.state = kind;
  };

  const renderTurnstile = () => {
    if (!widgetHost || !config.turnstileSiteKey || !window.turnstile?.render) return;
    turnstileId = window.turnstile.render(widgetHost, {
      sitekey: config.turnstileSiteKey,
      size: 'invisible',
      callback: (value) => { token = value || ''; },
      'expired-callback': () => { token = ''; },
      'error-callback': () => { token = ''; },
    });
  };

  if (!config.turnstileSiteKey) {
    setStatus(copy('The contact form is temporarily unavailable.', 'Kontaktní formulář je dočasně nedostupný.'), 'error');
  } else if (window.turnstile?.render) {
    renderTurnstile();
  } else {
    window.setTimeout(renderTurnstile, 500);
  }

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    if (!form.checkValidity()) {
      form.reportValidity();
      return;
    }
    if (!config.apiUrl || !token) {
      setStatus(copy('Please complete the security check and try again.', 'Dokončete bezpečnostní kontrolu a zkuste to znovu.'), 'error');
      return;
    }
    const data = Object.fromEntries(new FormData(form).entries());
    data.turnstile_token = token;
    submit?.setAttribute('disabled', 'disabled');
    setStatus(copy('Sending…', 'Odesílám…'));
    try {
      const response = await fetch(config.apiUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      });
      if (!response.ok) throw new Error('contact request failed');
      form.reset();
      token = '';
      if (turnstileId !== null && window.turnstile?.reset) window.turnstile.reset(turnstileId);
      setStatus(copy('Message sent. Thank you — we will reply by email.', 'Zpráva byla odeslána. Děkujeme — odpovíme e-mailem.'), 'success');
    } catch (_) {
      setStatus(copy('The message could not be sent. Please try again later.', 'Zprávu se nepodařilo odeslat. Zkuste to prosím později.'), 'error');
      token = '';
      if (turnstileId !== null && window.turnstile?.reset) window.turnstile.reset(turnstileId);
    } finally {
      submit?.removeAttribute('disabled');
    }
  });
})();
