(() => {
  const API = 'https://api.tomaspisar.cz';
  const { deriveDashboardEntitlement } = window.LJR_ACCOUNT_STATE;
  const page = document.body.dataset.portalPage;
  const state = { lang: document.documentElement.lang === 'cs' ? 'cs' : 'en', email: '', codeSent: false, account: null };
  const $ = (selector) => document.querySelector(selector);
  const copy = {
    en: {
      sending: 'Sending code…', checking: 'Checking code…', sent: 'A code is on the way. It is valid for 10 minutes.',
      invalidEmail: 'Enter a valid email address.', invalidCode: 'Enter the six-digit code from your email.',
      genericError: 'Something went wrong. Please try again.', noDevices: 'No activated computers.',
      noInvoices: 'No invoices available yet.', deactivate: 'Deactivate', deactivating: 'Deactivating…',
      deactivated: 'Computer deactivated.', statusActive: 'Active', statusInactive: 'Inactive',
      statusDeactivated: 'Deactivated', lifetime: 'Lifetime licence', subscription: 'Monthly subscription',
      devices: 'computers', purchased: 'Purchased', activated: 'Activated', paidThrough: 'Paid through', lastSync: 'Last server sync',
      invoice: 'Invoice', amount: 'Amount', date: 'Date', status: 'Status', available: 'available',
      lifetimeNote: 'No renewal required', subscriptionNote: 'Renews while active', notPurchased: 'Not purchased',
      subscriptionEnded: 'Subscription ended', noActiveLicence: 'No active licence',
      noLicenceEyebrow: 'NO LICENCE YET', noLicenceTitle: 'No licence purchased for this account.',
      noLicenceCopy: 'Buy with this email address and the licence will appear here automatically after payment.',
      inactiveLicenceEyebrow: 'NO ACTIVE LICENCE', inactiveLicenceTitle: 'No active licence for this account.',
      inactiveLicenceCopy: 'Your previous plan is inactive. Purchase again with this email address to restore access.',
      notApplicable: 'Not applicable', verificationReady: 'After activation', sessionExpired: 'Your session ended. Sign in again.'
    },
    cs: {
      sending: 'Odesílám kód…', checking: 'Ověřuji kód…', sent: 'Kód je na cestě. Platí 10 minut.',
      invalidEmail: 'Zadejte platnou e-mailovou adresu.', invalidCode: 'Zadejte šestimístný kód z e-mailu.',
      genericError: 'Něco se nepodařilo. Zkuste to znovu.', noDevices: 'Žádné aktivované počítače.',
      noInvoices: 'Zatím nejsou k dispozici žádné faktury.', deactivate: 'Deaktivovat', deactivating: 'Deaktivuji…',
      deactivated: 'Počítač byl deaktivován.', statusActive: 'Aktivní', statusInactive: 'Neaktivní',
      statusDeactivated: 'Deaktivováno', lifetime: 'Doživotní licence', subscription: 'Měsíční předplatné',
      devices: 'počítače', purchased: 'Zakoupeno', activated: 'Aktivováno', paidThrough: 'Zaplaceno do', lastSync: 'Poslední synchronizace',
      invoice: 'Faktura', amount: 'Částka', date: 'Datum', status: 'Stav', available: 'volná',
      lifetimeNote: 'Bez nutnosti obnovení', subscriptionNote: 'Obnovuje se, dokud je aktivní', notPurchased: 'Nezakoupeno',
      subscriptionEnded: 'Předplatné skončilo', noActiveLicence: 'Žádná aktivní licence',
      noLicenceEyebrow: 'ZATÍM BEZ LICENCE', noLicenceTitle: 'Pro tento účet zatím nebyla zakoupena licence.',
      noLicenceCopy: 'Nakupte s touto e-mailovou adresou a licence se zde po zaplacení zobrazí automaticky.',
      inactiveLicenceEyebrow: 'ŽÁDNÁ AKTIVNÍ LICENCE', inactiveLicenceTitle: 'Pro tento účet není aktivní žádná licence.',
      inactiveLicenceCopy: 'Předchozí plán je neaktivní. Pro obnovení přístupu nakupte znovu se stejnou e-mailovou adresou.',
      notApplicable: 'Nevztahuje se', verificationReady: 'Po aktivaci', sessionExpired: 'Relace skončila. Přihlaste se znovu.'
    }
  };

  class ApiError extends Error {
    constructor(message, status, code) { super(message); this.status = status; this.code = code; }
  }

  const t = (key) => copy[state.lang][key] || copy.en[key] || key;
  const escapeHtml = (value) => String(value ?? '').replace(/[&<>'"]/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[char]));
  const formatDate = (seconds) => seconds ? new Intl.DateTimeFormat(state.lang === 'cs' ? 'cs-CZ' : 'en-GB', { dateStyle: 'medium' }).format(new Date(seconds * 1000)) : '—';
  const formatDateTime = (seconds) => seconds ? new Intl.DateTimeFormat(state.lang === 'cs' ? 'cs-CZ' : 'en-GB', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(seconds * 1000)) : '—';
  const formatMoney = (amount, currency) => typeof amount === 'number' ? new Intl.NumberFormat(state.lang === 'cs' ? 'cs-CZ' : 'en-GB', { style: 'currency', currency: (currency || 'czk').toUpperCase() }).format(amount / 100) : '—';
  const setStatus = (message, selector = '#account-status') => { const element = $(selector); if (element) element.textContent = message || ''; };
  const api = async (path, options = {}) => {
    const response = await fetch(`${API}${path}`, {
      ...options,
      credentials: 'include',
      headers: { Accept: 'application/json', ...(options.body ? { 'Content-Type': 'application/json' } : {}), ...(options.headers || {}) }
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new ApiError(data.message || t('genericError'), response.status, data.error || 'error');
    return data;
  };

  const setLoginBusy = (busy) => {
    const button = $('#login-submit');
    if (!button) return;
    button.disabled = busy;
    button.setAttribute('aria-busy', String(busy));
  };

  const initLogin = () => {
    const form = $('#login-form');
    if (!form) return;

    const requestCode = async () => {
      const email = $('#email').value.trim();
      if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) { setStatus(t('invalidEmail'), '#login-status'); return; }
      state.email = email;
      setStatus(t('sending'), '#login-status');
      setLoginBusy(true);
      try {
        await api('/api/portal/request-code', { method: 'POST', body: JSON.stringify({ email }) });
        state.codeSent = true;
        $('#code-field').hidden = false;
        $('#login-submit').textContent = state.lang === 'cs' ? 'Přihlásit' : 'Sign in';
        setStatus(t('sent'), '#login-status');
        $('#code').focus();
      } catch (error) { setStatus(error.message, '#login-status'); }
      finally { setLoginBusy(false); }
    };

    const verifyCode = async () => {
      const code = $('#code').value.trim();
      if (!/^\d{6}$/.test(code)) { setStatus(t('invalidCode'), '#login-status'); return; }
      setStatus(t('checking'), '#login-status');
      setLoginBusy(true);
      try {
        await api('/api/portal/verify-code', { method: 'POST', body: JSON.stringify({ email: state.email, code }) });
        window.location.replace('/dashboard');
      } catch (error) { setStatus(error.message, '#login-status'); }
      finally { setLoginBusy(false); }
    };

    form.addEventListener('submit', (event) => { event.preventDefault(); state.codeSent ? verifyCode() : requestCode(); });
    api('/api/portal/account').then(() => window.location.replace('/dashboard')).catch(() => $('#email').focus());
  };

  const renderLicenceCards = (licences) => {
    $('#licence-cards').innerHTML = licences.map((licence) => {
      const active = licence.status === 'active';
      const activeDevices = active ? (licence.active_devices || 0) : 0;
      const availableSlots = active ? licence.max_devices : 0;
      return `
      <article class="licence-card">
        <div class="licence-card-heading"><span class="badge ${active ? '' : 'warn'}">${active ? t('statusActive') : t('statusInactive')}</span><span class="licence-id">LongJumpReplay</span></div>
        <h3>${licence.type === 'subscription' ? t('subscription') : t('lifetime')}</h3>
        <dl>
          <div><dt>${t('devices')}</dt><dd>${activeDevices} / ${availableSlots}</dd></div>
          <div><dt>${t('purchased')}</dt><dd>${formatDate(licence.created_at)}</dd></div>
          ${licence.current_period_end ? `<div><dt>${t('paidThrough')}</dt><dd>${formatDate(licence.current_period_end)}</dd></div>` : ''}
          <div><dt>${t('lastSync')}</dt><dd>${formatDate(licence.last_stripe_sync)}</dd></div>
        </dl>
      </article>`;
    }).join('');
  };

  const renderDevices = (devices, activeLicenceIds) => {
    $('#devices-list').innerHTML = devices.length ? devices.map((device) => {
      const active = device.status === 'active' && activeLicenceIds.has(device.license_id);
      const nextCheck = active && device.last_verified_at ? device.last_verified_at + (30 * 86400) : null;
      return `<article class="device-card">
        <div class="device-icon" aria-hidden="true">▰</div>
        <div><div class="device-heading"><h3>${escapeHtml(device.device_name || 'LongJumpReplay computer')}</h3><span class="badge ${active ? '' : 'warn'}">${active ? t('statusActive') : t('statusDeactivated')}</span></div>
        <p>${t('activated')}: <strong>${formatDateTime(device.activated_at)}</strong> · ${t('lastSync')}: <strong>${formatDate(device.last_verified_at)}</strong></p>
        ${nextCheck ? `<p>${state.lang === 'cs' ? 'Online ověření do' : 'Online verification by'} <strong>${formatDate(nextCheck)}</strong></p>` : ''}</div>
        ${active ? `<button class="small-button" type="button" data-deactivate="${escapeHtml(device.id)}">${t('deactivate')}</button>` : ''}
      </article>`;
    }).join('') : `<div class="empty">${t('noDevices')}</div>`;
  };

  const renderInvoices = (invoices) => {
    $('#invoices').innerHTML = invoices.length ? `<table class="data-table"><thead><tr><th>${t('invoice')}</th><th>${t('date')}</th><th>${t('amount')}</th><th>${t('status')}</th></tr></thead><tbody>${invoices.map((invoice) => `<tr><td>${invoice.hosted_invoice_url ? `<a href="${escapeHtml(invoice.hosted_invoice_url)}" target="_blank" rel="noopener">${escapeHtml(invoice.id)}</a>` : escapeHtml(invoice.id)}</td><td>${formatDate(invoice.created)}</td><td>${formatMoney(invoice.amount_paid, invoice.currency)}</td><td>${escapeHtml(invoice.status || '—')}</td></tr>`).join('')}</tbody></table>` : `<div class="empty">${t('noInvoices')}</div>`;
  };

  const renderDashboard = (data) => {
    state.account = data;
    const licences = data.licenses || [];
    const devices = data.devices || [];
    const {
      activeLicenceIds, activeDevices, totalSlots, primary, hasAnyLicence, hasActiveLicence,
    } = deriveDashboardEntitlement(licences, devices);
    const nextVerification = activeDevices.map((device) => device.last_verified_at || device.activated_at || 0).filter(Boolean).sort((a, b) => a - b)[0];

    $('#customer-email').textContent = data.customer?.email || '—';
    $('#summary-licence').textContent = hasActiveLicence
      ? (primary.type === 'subscription' ? t('subscription') : t('lifetime'))
      : t('noActiveLicence');
    $('#summary-licence-note').textContent = primary ? (primary.status === 'active' ? t('statusActive') : t('statusInactive')) : (state.lang === 'cs' ? 'Připraveno k nákupu' : 'Ready when you purchase');
    $('#summary-devices').textContent = `${activeDevices.length} / ${totalSlots}`;
    $('#summary-plan-date').textContent = primary?.current_period_end ? formatDate(primary.current_period_end) : (primary?.type === 'lifetime' ? formatDate(primary.created_at) : '—');
    $('#summary-plan-note').textContent = primary
      ? (primary.type === 'subscription' ? (primary.status === 'active' ? t('subscriptionNote') : t('subscriptionEnded')) : t('lifetimeNote'))
      : t('notApplicable');
    $('#summary-verification').textContent = nextVerification ? formatDate(nextVerification + (30 * 86400)) : t('verificationReady');
    $('#session-expiry').textContent = formatDate(data.session_expires_at);

    $('#no-licence-state').hidden = hasActiveLicence;
    $('#no-licence-eyebrow').textContent = t(hasAnyLicence ? 'inactiveLicenceEyebrow' : 'noLicenceEyebrow');
    $('#no-licence-title').textContent = t(hasAnyLicence ? 'inactiveLicenceTitle' : 'noLicenceTitle');
    $('#no-licence-copy').textContent = t(hasAnyLicence ? 'inactiveLicenceCopy' : 'noLicenceCopy');
    $('#licence-cards').hidden = !hasAnyLicence;
    document.querySelectorAll('.licensed-only').forEach((section) => { section.hidden = !hasAnyLicence; });
    $('#billing-button').hidden = !data.billing?.customer_portal_available;
    $('#device-count').textContent = `${activeDevices.length} ${state.lang === 'cs' ? 'aktivní' : 'active'} · ${Math.max(0, totalSlots - activeDevices.length)} ${t('available')}`;
    renderLicenceCards(licences);
    renderDevices(devices, activeLicenceIds);
    renderInvoices(data.invoices || []);
    $('#dashboard-loading').hidden = true;
    $('#dashboard-content').hidden = false;
  };

  const loadDashboard = async () => {
    try { renderDashboard(await api('/api/portal/account')); }
    catch (error) {
      if (error.status === 401) window.location.replace('/login');
      else { $('#dashboard-loading').hidden = true; setStatus(error.message); }
    }
  };

  const deactivate = async (deviceId) => {
    if (!window.confirm(state.lang === 'cs' ? 'Opravdu deaktivovat tento počítač?' : 'Deactivate this computer?')) return;
    setStatus(t('deactivating'));
    try {
      await api('/api/portal/deactivate-device', { method: 'POST', body: JSON.stringify({ device_id: deviceId }) });
      setStatus(t('deactivated'));
      await loadDashboard();
    } catch (error) { setStatus(error.message); }
  };

  const signOut = async () => {
    try { await api('/api/portal/logout', { method: 'POST', body: '{}' }); }
    finally { window.location.replace('/login'); }
  };

  const initDashboard = () => {
    document.addEventListener('click', (event) => {
      const button = event.target.closest('[data-deactivate]');
      if (button) deactivate(button.dataset.deactivate);
    });
    $('#billing-button')?.addEventListener('click', async () => {
      setStatus(t('sending'));
      try { const data = await api('/api/portal/billing', { method: 'POST', body: '{}' }); window.location.href = data.url; }
      catch (error) { setStatus(error.message); }
    });
    $('#logout-button')?.addEventListener('click', signOut);
    $('#security-logout-button')?.addEventListener('click', signOut);
    loadDashboard();
  };

  document.querySelector('[data-lang-toggle]')?.addEventListener('click', () => window.setTimeout(() => {
    state.lang = document.documentElement.lang === 'cs' ? 'cs' : 'en';
    if (state.account && page === 'dashboard') renderDashboard(state.account);
    if (state.codeSent && page === 'login') $('#login-submit').textContent = state.lang === 'cs' ? 'Přihlásit' : 'Sign in';
  }, 0));

  if (page === 'login') initLogin();
  if (page === 'dashboard') initDashboard();
})();
