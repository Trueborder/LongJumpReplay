(() => {
  const form = document.querySelector('[data-contact-form]');
  if (!form) return;
  const config = window.SITE_CONFIG?.contact || {};
  const status = document.querySelector('[data-contact-status]');
  const submit = form.querySelector('button[type="submit"]');
  const widgetHost = form.querySelector('[data-contact-turnstile]');
  const productField = form.elements.namedItem('product');
  const topicField = form.elements.namedItem('topic');
  const messageField = form.elements.namedItem('message');
  const feedback = window.LJR_FEEDBACK;
  let turnstileId = null;
  let token = '';
  const copy = (en, cs) => document.documentElement.lang === 'cs' ? cs : en;
  const topics = {
    longjumpreplay: [['support','Product support','Podpora produktu'],['licence','Licence or pricing','Licence nebo cena'],['club','Club or team pricing','Klubová nebo týmová cena'],['bug','Bug report','Nahlášení chyby'],['feedback','Feature request','Návrh na funkci'],['general','Other question','Jiný dotaz']],
    relaylab: [['support','Setup or access','Nastavení nebo přístup'],['bug','Bug report','Nahlášení chyby'],['feedback','Feature request','Návrh na funkci'],['general','Other question','Jiný dotaz']],
    economysuite: [['support','Setup or compatibility','Nastavení nebo kompatibilita'],['licence','Build or access question','Dotaz k sestavení nebo přístupu'],['bug','Bug report','Nahlášení chyby'],['feedback','Feature request','Návrh na funkci'],['general','Other question','Jiný dotaz']],
    custom: [['general','New project or estimate','Nový projekt nebo odhad ceny'],['support','Support for an existing project','Podpora existujícího projektu'],['bug','Bug report','Nahlášení chyby'],['feedback','Change request','Požadavek na změnu']],
    other: [['support','Product support','Podpora produktu'],['bug','Bug report','Nahlášení chyby'],['feedback','Feedback or feature idea','Zpětná vazba nebo nápad na funkci'],['general','Other question','Jiný dotaz']],
  };
  const renderTopicOptions = () => {
    if (!topicField) return;
    const choices = topics[productField?.value] || [];
    topicField.replaceChildren(new Option('', '', true, true));
    topicField.disabled = choices.length === 0;
    choices.forEach(([value, en, cs]) => {
      const option = new Option(copy(en, cs), value);
      option.dataset.en = en;
      option.dataset.cs = cs;
      topicField.add(option);
    });
  };
  const updateMessageLimit = () => {
    const product = productField?.selectedOptions?.[0]?.textContent?.trim() || '';
    const prefix = product ? `Product: ${product}\n\n` : '';
    if (messageField) messageField.maxLength = 5000 - prefix.length;
  };
  const selectProductFromLink = () => {
    if (!productField) return;
    const requested = new URLSearchParams(window.location.search).get('product');
    if (requested && [...productField.options].some((option) => option.value === requested)) productField.value = requested;
    renderTopicOptions();
    updateMessageLimit();
  };
  productField?.addEventListener('change', () => { renderTopicOptions(); updateMessageLimit(); });
  form.addEventListener('reset', () => window.setTimeout(() => { renderTopicOptions(); updateMessageLimit(); }, 0));
  selectProductFromLink();
  const setStatus = (message, kind = '') => feedback?.inline(status, message, kind || 'info');
  const renderTurnstile = () => {
    if (!widgetHost || !config.turnstileSiteKey || !window.turnstile?.render) return;
    turnstileId = window.turnstile.render(widgetHost, { sitekey: config.turnstileSiteKey, size: 'invisible', callback: (value) => { token = value || ''; }, 'expired-callback': () => { token = ''; }, 'error-callback': () => { token = ''; } });
  };
  if (!config.turnstileSiteKey) setStatus(copy('The contact form is temporarily unavailable. Please email support instead.', 'Kontaktní formulář je dočasně nedostupný. Napište nám prosím e-mailem.'), 'error');
  else if (window.turnstile?.render) renderTurnstile();
  else window.setTimeout(renderTurnstile, 500);
  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    if (!form.checkValidity()) { form.reportValidity(); return; }
    if (!config.apiUrl || !token) { setStatus(copy('Complete the security check, then try sending the message again.', 'Dokončete bezpečnostní kontrolu a odešlete zprávu znovu.'), 'error'); return; }
    const data = Object.fromEntries(new FormData(form).entries());
    const product = productField?.selectedOptions?.[0]?.textContent?.trim();
    if (product) data.message = `Product: ${product}\n\n${data.message}`;
    data.turnstile_token = token;
    submit?.setAttribute('disabled', 'disabled');
    setStatus(copy('Sending…', 'Odesílám…'), 'info');
    try {
      const response = await fetch(config.apiUrl, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) });
      if (!response.ok) throw new Error('contact request failed');
      form.reset(); token = '';
      if (turnstileId !== null && window.turnstile?.reset) window.turnstile.reset(turnstileId);
      setStatus('', '');
      feedback?.toast.success(copy('Support request sent. We will reply by email.', 'Žádost o podporu byla odeslána. Odpovíme e-mailem.'), { title: copy('Ticket sent', 'Ticket odeslán') });
    } catch (_) {
      setStatus(copy('The message could not be sent. Check your connection and try again.', 'Zprávu se nepodařilo odeslat. Zkontrolujte připojení a zkuste to znovu.'), 'error');
      token = '';
      if (turnstileId !== null && window.turnstile?.reset) window.turnstile.reset(turnstileId);
    } finally { submit?.removeAttribute('disabled'); }
  });
})();