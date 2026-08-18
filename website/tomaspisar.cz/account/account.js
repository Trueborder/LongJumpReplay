(() => {
  const API = 'https://api.tomaspisar.cz';
  const state = { lang: document.documentElement.lang === 'cs' ? 'cs' : 'en', email: '', codeSent: false, account: null };
  const $ = (selector) => document.querySelector(selector);
  const copy = {
    en: {
      sending: 'Sending code…', checking: 'Checking code…',
      sent: 'A code is on the way. It is valid for 10 minutes.',
      signedIn: 'Signed in.', invalidEmail: 'Enter a valid email address.',
      genericError: 'Something went wrong. Please try again.', noDevices: 'No activated computers.',
      noInvoices: 'No invoices available yet.', deactivate: 'Deactivate', deactivating: 'Deactivating…',
      deactivated: 'Device deactivated.', signIn: 'Sign in to view your account.',
      billingUnavailable: 'Billing management is not available for this account yet.',
      statusActive: 'Active', statusInactive: 'Inactive', statusDeactivated: 'Deactivated',
      lifetime: 'Lifetime licence', subscription: 'Monthly subscription', devices: 'devices',
      paidThrough: 'Paid through', created: 'Purchased', lastSync: 'Last server check',
      manage: 'Manage billing', invoice: 'Invoice', amount: 'Amount', date: 'Date', status: 'Status'
    },
    cs: {
      sending: 'Odesílání kódu…', checking: 'Ověřování kódu…',
      sent: 'Kód je na cestě. Platí 10 minut.',
      signedIn: 'Přihlášení proběhlo.', invalidEmail: 'Zadejte platnou e-mailovou adresu.',
      genericError: 'Něco se nepodařilo. Zkuste to znovu.', noDevices: 'Žádné aktivované počítače.',
      noInvoices: 'Zatím nejsou k dispozici žádné faktury.', deactivate: 'Deaktivovat', deactivating: 'Deaktivace…',
      deactivated: 'Zařízení deaktivováno.', signIn: 'Přihlaste se pro zobrazení účtu.',
      billingUnavailable: 'Správa plateb pro tento účet zatím není dostupná.',
      statusActive: 'Aktivní', statusInactive: 'Neaktivní', statusDeactivated: 'Deaktivováno',
      lifetime: 'Doživotní licence', subscription: 'Měsíční předplatné', devices: 'zařízení',
      paidThrough: 'Zaplaceno do', created: 'Zakoupeno', lastSync: 'Poslední kontrola serveru',
      manage: 'Spravovat platby', invoice: 'Faktura', amount: 'Částka', date: 'Datum', status: 'Stav'
    }
  };
  const t = (key) => copy[state.lang][key] || copy.en[key] || key;
  const formatDate = (seconds) => seconds ? new Intl.DateTimeFormat(state.lang === 'cs' ? 'cs-CZ' : 'en-GB', { dateStyle: 'medium' }).format(new Date(seconds * 1000)) : '—';
  const formatMoney = (amount, currency) => typeof amount === 'number' ? new Intl.NumberFormat(state.lang === 'cs' ? 'cs-CZ' : 'en-GB', { style: 'currency', currency: (currency || 'czk').toUpperCase() }).format(amount / 100) : '—';
  const escapeHtml = (value) => String(value ?? '').replace(/[&<>'"]/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[char]));
  const setStatus = (message, target = '#login-status') => { const element = $(target); if (element) element.textContent = message || ''; };
  const setLoginBusy = (busy) => {
    const button = $('#login-submit');
    button.disabled = busy;
    button.setAttribute('aria-busy', String(busy));
  };
  const api = async (path, options = {}) => {
    const response = await fetch(`${API}${path}`, { ...options, credentials: 'include', headers: { Accept: 'application/json', ...(options.body ? { 'Content-Type': 'application/json' } : {}), ...(options.headers || {}) } });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.message || t('genericError'));
    return data;
  };

  const showAccount = (visible) => { $('#login-view').hidden = visible; $('#account-view').hidden = !visible; $('#logout-button').hidden = !visible; };
  const requestCode = async () => {
    const email = $('#email').value.trim();
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) { setStatus(t('invalidEmail')); return; }
    state.email = email; setStatus(t('sending')); setLoginBusy(true);
    try {
      await api('/api/portal/request-code', { method: 'POST', body: JSON.stringify({ email }) });
      state.codeSent = true; $('#code-field').hidden = false; $('#code').focus();
      $('#login-submit').textContent = state.lang === 'cs' ? 'Přihlásit' : 'Sign in'; setStatus(t('sent'));
    } catch (error) { setStatus(error.message); }
    finally { setLoginBusy(false); }
  };
  const verifyCode = async () => {
    const code = $('#code').value.trim();
    if (!/^\d{6}$/.test(code)) { setStatus(state.lang === 'cs' ? 'Zadejte šestimístný kód.' : 'Enter the six-digit code.'); return; }
    setStatus(t('checking')); setLoginBusy(true);
    try { await api('/api/portal/verify-code', { method: 'POST', body: JSON.stringify({ email: state.email, code }) }); showAccount(true); setStatus(''); await loadAccount(); }
    catch (error) { setStatus(error.message); }
    finally { setLoginBusy(false); }
  };
  $('#login-form').addEventListener('submit', (event) => { event.preventDefault(); state.codeSent ? verifyCode() : requestCode(); });

  const renderAccount = (data) => {
    state.account = data; $('#customer-email').textContent = data.customer?.email || '';
    const licences = data.licenses || [];
    const hasLicence = licences.length > 0;
    $('#no-licence-state').hidden = hasLicence;
    $('#licence-cards').hidden = !hasLicence;
    document.querySelectorAll('.licensed-only').forEach((section) => { section.hidden = !hasLicence; });
    $('#licence-cards').innerHTML = licences.map((licence) => `<article class="licence-card"><span class="badge ${licence.status === 'active' ? '' : 'warn'}">${licence.status === 'active' ? t('statusActive') : t('statusInactive')}</span><h3>${licence.type === 'subscription' ? t('subscription') : t('lifetime')}</h3><p><span class="value">${licence.active_devices || 0} / ${licence.max_devices}</span> ${t('devices')}</p><p>${t('created')}: <span class="value">${formatDate(licence.created_at)}</span></p>${licence.current_period_end ? `<p>${t('paidThrough')}: <span class="value">${formatDate(licence.current_period_end)}</span></p>` : ''}<p>${t('lastSync')}: <span class="value">${formatDate(licence.last_stripe_sync)}</span></p></article>`).join('');
    const devices = data.devices || [];
    $('#device-count').textContent = `${devices.filter((device) => device.status === 'active').length} / ${licences.reduce((sum, licence) => sum + licence.max_devices, 0) || 0}`;
    $('#devices').innerHTML = devices.length ? `<table class="data-table"><thead><tr><th>Computer</th><th>Status</th><th>Activated</th><th>Last check</th><th></th></tr></thead><tbody>${devices.map((device) => `<tr><td>${escapeHtml(device.device_name || 'LongJumpReplay computer')}</td><td>${device.status === 'active' ? t('statusActive') : t('statusDeactivated')}</td><td>${formatDate(device.activated_at)}</td><td>${formatDate(device.last_verified_at)}</td><td>${device.status === 'active' ? `<button class="small-button" data-deactivate="${escapeHtml(device.id)}">${t('deactivate')}</button>` : ''}</td></tr>`).join('')}</tbody></table>` : `<div class="empty">${t('noDevices')}</div>`;
    const invoices = data.invoices || [];
    $('#invoices').innerHTML = invoices.length ? `<table class="data-table"><thead><tr><th>${t('invoice')}</th><th>${t('date')}</th><th>${t('amount')}</th><th>${t('status')}</th></tr></thead><tbody>${invoices.map((invoice) => `<tr><td>${invoice.hosted_invoice_url ? `<a href="${escapeHtml(invoice.hosted_invoice_url)}" target="_blank" rel="noopener">${escapeHtml(invoice.id)}</a>` : escapeHtml(invoice.id)}</td><td>${formatDate(invoice.created)}</td><td>${formatMoney(invoice.amount_paid, invoice.currency)}</td><td>${escapeHtml(invoice.status || '—')}</td></tr>`).join('')}</tbody></table>` : `<div class="empty">${t('noInvoices')}</div>`;
    $('#billing-button').hidden = !data.billing?.customer_portal_available;
    document.querySelectorAll('[data-deactivate]').forEach((button) => button.addEventListener('click', () => deactivate(button.dataset.deactivate)));
  };
  const loadAccount = async () => { try { renderAccount(await api('/api/portal/account')); } catch (error) { if (error.message.includes('Sign in')) { showAccount(false); } else setStatus(error.message, '#account-status'); } };
  const deactivate = async (deviceId) => { if (!window.confirm(state.lang === 'cs' ? 'Opravdu deaktivovat toto zařízení?' : 'Deactivate this device?')) return; setStatus(t('deactivating'), '#account-status'); try { await api('/api/portal/deactivate-device', { method: 'POST', body: JSON.stringify({ device_id: deviceId }) }); setStatus(t('deactivated'), '#account-status'); await loadAccount(); } catch (error) { setStatus(error.message, '#account-status'); } };
  $('#billing-button').addEventListener('click', async () => { setStatus(t('sending'), '#account-status'); try { const data = await api('/api/portal/billing', { method: 'POST', body: '{}' }); window.location.href = data.url; } catch (error) { setStatus(error.message, '#account-status'); } });
  $('#logout-button').addEventListener('click', async () => { try { await api('/api/portal/logout', { method: 'POST', body: '{}' }); } finally { showAccount(false); $('#code-field').hidden = true; state.codeSent = false; setStatus(''); } });
  document.querySelector('[data-lang-toggle]')?.addEventListener('click', () => { window.setTimeout(() => { state.lang = document.documentElement.lang === 'cs' ? 'cs' : 'en'; if (state.account) renderAccount(state.account); }, 0); });
  showAccount(false);
  api('/api/portal/account').then((data) => { showAccount(true); renderAccount(data); }).catch(() => showAccount(false));
})();
