(() => {
  const root = document.querySelector('#ljr-public-catalog');
  if (!root) return;
  const API = 'https://api.tomaspisar.cz/api/longjumpreplay';
  const dialog = document.querySelector('#ljr-purchase-dialog');
  const form = dialog.querySelector('form');
  const submit = dialog.querySelector('[type="submit"]');
  const status = dialog.querySelector('#purchase-status');
  const text = (en, cs) => document.documentElement.lang === 'cs' ? cs : en;
  const escapeHtml = value => String(value ?? '').replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
  const money = item => new Intl.NumberFormat(text('en-GB', 'cs-CZ'), {style:'currency', currency:item.currency.toUpperCase()}).format(item.amount_minor / 100);
  const name = item => item.license_type === 'subscription' ? text('Monthly licence', 'Měsíční licence') : text('Lifetime licence', 'Doživotní licence');
  let items = [];
  let selected = null;
  let busy = false;
  let trigger = null;
  const keys = new Map();
  const summary = () => {
    if (!selected) return;
    dialog.querySelector('#purchase-plan').textContent = name(selected);
    dialog.querySelector('#purchase-price').textContent = money(selected) + (selected.license_type === 'subscription' ? text(' / month', ' / měsíc') : '');
    dialog.querySelector('#purchase-detail').textContent = `${selected.device_limit} ${text('computers', 'počítače')} · ${text('Offline verification up to', 'Offline ověření až')} ${selected.offline_verification_days} ${text('days', 'dnů')}`;
    dialog.querySelector('#purchase-tax').textContent = selected.tax_notice && !selected.tax_notice.includes('[[')
      ? selected.tax_notice : text('The final total is shown in Stripe Checkout.', 'Konečnou částku uvidíte v pokladně Stripe.');
    dialog.querySelector('#purchase-renewal').textContent = selected.license_type === 'subscription'
      ? text('Renews monthly until cancelled. Access continues until the end of the paid period.', 'Obnovuje se každý měsíc do zrušení. Přístup trvá do konce zaplaceného období.')
      : text('One payment. Your licence never expires.', 'Jednorázová platba. Licence nikdy nevyprší.');
  };
  const close = () => { if (!busy) dialog.close(); };
  dialog.querySelector('[data-purchase-close]').addEventListener('click', close);
  dialog.addEventListener('click', event => {
    if (event.target !== dialog) return;
    const rect = dialog.getBoundingClientRect();
    if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) close();
  });
  dialog.addEventListener('cancel', event => { if (busy) event.preventDefault(); });
  dialog.addEventListener('close', () => { document.body.classList.remove('purchase-open'); trigger?.focus(); });
  root.addEventListener('click', event => {
    const button = event.target.closest('[data-purchase-price]');
    if (!button || busy) return;
    selected = items.find(item => item.price_id === button.dataset.purchasePrice);
    if (!selected) return;
    trigger = button;
    trigger.focus();
    form.reset();
    status.textContent = '';
    summary();
    document.body.classList.add('purchase-open');
    window.LJR_FEEDBACK?.bindDialog(dialog);
    dialog.showModal();
  });
  form.addEventListener('submit', async event => {
    event.preventDefault();
    if (!selected || busy || !form.reportValidity()) return;
    busy = true;
    submit.disabled = true;
    submit.setAttribute('aria-busy', 'true');
    status.dataset.state = 'info';
    status.textContent = text('Opening secure checkout…', 'Otevírám zabezpečenou platbu…');
    const priceId = selected.price_id;
    if (!keys.has(priceId)) keys.set(priceId, `ljr_${crypto.randomUUID().replaceAll('-', '')}`);
    try {
      const response = await fetch(`${API}/checkout`, {
        method:'POST', headers:{'Content-Type':'application/json','X-Idempotency-Key':keys.get(priceId)},
        body:JSON.stringify({price_id:priceId, accepted_purchase_terms:form.querySelector('#purchase-terms').checked,
          immediate_delivery_requested:form.querySelector('#delivery-consent').checked, withdrawal_rights_acknowledged:form.querySelector('#withdrawal-consent').checked})
      });
      const data = await response.json();
      if (!response.ok || typeof data.url !== 'string' || !data.url.startsWith('https://checkout.stripe.com/')) throw new Error();
      location.assign(data.url);
    } catch {
      status.dataset.state = 'error';
      status.textContent = text('Checkout could not be opened. Please try again.', 'Platbu se nepodařilo otevřít. Zkuste to znovu.');
      busy = false;
      submit.disabled = false;
      submit.removeAttribute('aria-busy');
    }
  });
  const render = () => {
    root.innerHTML = items.map(item => `<article class="buy-option"><p class="eyebrow">${item.license_type === 'subscription' ? text('MONTHLY','MĚSÍČNÍ') : text('LIFETIME','DOŽIVOTNÍ')}</p><h3>${name(item)}</h3><strong class="buy-option-price">${money(item)}${item.license_type === 'subscription' ? text(' / month',' / měsíc') : ''}</strong><p>${item.device_limit} ${text('computers, email activation, offline verification up to','počítače, aktivace e-mailem, offline ověření až')} ${item.offline_verification_days} ${text('days.','dnů.')}</p><button type="button" class="button button-primary" data-purchase-price="${escapeHtml(item.price_id)}" aria-haspopup="dialog" aria-controls="ljr-purchase-dialog">${text('Buy licence →','Koupit licenci →')}</button></article>`).join('') || `<p class="notice">${text('Prices are temporarily unavailable. Please contact support.','Ceník je dočasně nedostupný. Kontaktujte podporu.')}</p>`;
  };
  new MutationObserver(() => { if (items.length) render(); summary(); }).observe(document.documentElement, {attributes:true, attributeFilter:['lang']});
  fetch(`${API}/catalog`).then(response => response.ok ? response.json() : Promise.reject()).then(data => {
    items = (data.items || []).filter(item => Number.isInteger(item.amount_minor));
    render();
  }).catch(() => { root.innerHTML = `<p class="notice">${text('Prices could not be loaded. Please try again later or contact support.','Aktuální ceny se nepodařilo načíst. Zkuste to později nebo kontaktujte podporu.')}</p>`; });
})();
