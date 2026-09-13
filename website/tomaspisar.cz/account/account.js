(() => {
  const API = 'https://api.tomaspisar.cz';
  const { deriveDashboardEntitlement, deriveDevicePortalState } = window.LJR_ACCOUNT_STATE;
  const page = document.body.dataset.portalPage;
  const dashboardRoute = page === 'dashboard' ? (window.location.pathname.split('/').filter(Boolean)[1] || 'overview') : '';
  const dashboardRoutes = new Set(['overview', 'licence', 'activation-key', 'activation', 'devices', 'billing', 'help']);
  const state = { lang: document.documentElement.lang === 'cs' ? 'cs' : 'en', email: '', codeSent: false, account: null,
    keyVisible: false, keyValue: '', keyLicenceId: '', ensuredKeys: new Set(), pairing: null };
  const $ = (selector) => document.querySelector(selector);
  const copy = {
    en: {
      expiredCode: 'This code has expired. Request a new one.', verified: 'Verified. Opening your account…',
      sending: 'Sending code…', checking: 'Checking code…', sent: 'A code is on the way. It is valid for 10 minutes.',
      invalidEmail: 'Enter a valid email address.', invalidCode: 'Enter the six-digit code from your email.',
      genericError: 'Something went wrong. Please try again.', noDevices: 'No activated computers.',
      noInvoices: 'No invoices available yet.', deactivate: 'Deactivate', deactivating: 'Deactivating…',
      deactivated: 'Computer deactivated.', statusActive: 'Active', statusInactive: 'Inactive',
      statusDeactivated: 'Deactivated', statusLicenceInactive: 'Inactive licence', lifetime: 'Lifetime licence', subscription: 'Monthly subscription',
      devices: 'computers', purchased: 'Purchased', activated: 'Activated', paidThrough: 'Paid through', lastSync: 'Last server sync',
      invoice: 'Invoice', amount: 'Amount', date: 'Date', status: 'Status', available: 'available',
      lifetimeNote: 'No renewal required', subscriptionNote: 'Renews while active', notPurchased: 'Not purchased',
      subscriptionEnded: 'Subscription ended', noActiveLicence: 'No active licence',
      noLicenceEyebrow: 'NO LICENCE YET', noLicenceTitle: 'No licence purchased for this account.',
      noLicenceCopy: 'Buy with this email address and the licence will appear here automatically after payment.',
      inactiveLicenceEyebrow: 'NO ACTIVE LICENCE', inactiveLicenceTitle: 'No active licence for this account.',
      inactiveLicenceCopy: 'Your previous plan is inactive. Purchase again with this email address to restore access.',
      notApplicable: 'Not applicable', additionalTitle: 'Additional computers', addUpTo: 'You can add up to', usedOf: 'computers used', computer: 'Computer', purchase: 'Purchase securely with Stripe', quantity: 'Quantity', verificationReady: 'After activation', sessionExpired: 'Your session ended. Sign in again.',
      method: 'Method', lastActive: 'Last active', actions: 'Actions', details: 'Details', delete: 'Delete', emailMethod: 'Email', keyMethod: 'Key',
      pairingRequired: 'Enter the six-digit code shown by LongJumpReplay or open the QR link.', pairingFound: 'Computer found. Choose an active licence with an available slot.', pairingApproved: 'Approved. The app can finish activation now.', pairingNoCapacity: 'No active licence has an available computer slot.', pairingExpired: 'This pairing request is missing or expired.', pairingSameMachine: 'Already used by this computer', pairingAvailable: 'available slot', pairingApprove: 'Approve and activate'
    },
    cs: {
      expiredCode: 'Kód vypršel. Požádejte o nový.', verified: 'Ověřeno. Otevírám účet…',
      sending: 'Odesílám kód…', checking: 'Ověřuji kód…', sent: 'Kód je na cestě. Platí 10 minut.',
      invalidEmail: 'Zadejte platnou e-mailovou adresu.', invalidCode: 'Zadejte šestimístný kód z e-mailu.',
      genericError: 'Něco se nepodařilo. Zkuste to znovu.', noDevices: 'Žádné aktivované počítače.',
      noInvoices: 'Zatím nejsou k dispozici žádné faktury.', deactivate: 'Deaktivovat', deactivating: 'Deaktivuji…',
      deactivated: 'Počítač byl deaktivován.', statusActive: 'Aktivní', statusInactive: 'Neaktivní',
      statusDeactivated: 'Deaktivováno', statusLicenceInactive: 'Neaktivní licence', lifetime: 'Doživotní licence', subscription: 'Měsíční předplatné',
      devices: 'počítače', purchased: 'Zakoupeno', activated: 'Aktivováno', paidThrough: 'Zaplaceno do', lastSync: 'Poslední synchronizace',
      invoice: 'Faktura', amount: 'Částka', date: 'Datum', status: 'Stav', available: 'volná',
      lifetimeNote: 'Bez nutnosti obnovení', subscriptionNote: 'Obnovuje se, dokud je aktivní', notPurchased: 'Nezakoupeno',
      subscriptionEnded: 'Předplatné skončilo', noActiveLicence: 'Žádná aktivní licence',
      noLicenceEyebrow: 'ZATÍM BEZ LICENCE', noLicenceTitle: 'Pro tento účet zatím nebyla zakoupena licence.',
      noLicenceCopy: 'Nakupte s touto e-mailovou adresou a licence se zde po zaplacení zobrazí automaticky.',
      inactiveLicenceEyebrow: 'ŽÁDNÁ AKTIVNÍ LICENCE', inactiveLicenceTitle: 'Pro tento účet není aktivní žádná licence.',
      inactiveLicenceCopy: 'Předchozí plán je neaktivní. Pro obnovení přístupu nakupte znovu se stejnou e-mailovou adresou.',
      notApplicable: 'Nevztahuje se', additionalTitle: 'Další počítače', addUpTo: 'Můžete přidat až', usedOf: 'počítače využity', computer: 'Počítač', purchase: 'Bezpečně zaplatit přes Stripe', quantity: 'Počet', verificationReady: 'Po aktivaci', sessionExpired: 'Relace skončila. Přihlaste se znovu.',
      method: 'Způsob', lastActive: 'Poslední aktivita', actions: 'Akce', details: 'Podrobnosti', delete: 'Smazat', emailMethod: 'E-mail', keyMethod: 'Klíč',
      pairingRequired: 'Zadejte šestimístný kód z LongJumpReplay nebo otevřete QR odkaz.', pairingFound: 'Počítač nalezen. Vyberte aktivní licenci s volným místem.', pairingApproved: 'Schváleno. Aplikace nyní dokončí aktivaci.', pairingNoCapacity: 'Žádná aktivní licence nemá volné místo pro počítač.', pairingExpired: 'Párování chybí nebo vypršelo.', pairingSameMachine: 'Tento počítač je již použit', pairingAvailable: 'volné místo', pairingApprove: 'Schválit a aktivovat'
    }
  };

  class ApiError extends Error {
    constructor(message, status, code) { super(message); this.status = status; this.code = code; }
  }

  const t = (key) => copy[state.lang][key] || copy.en[key] || key;
  const routeCopy = {
    en: {
      overview: ['ACCOUNT OVERVIEW', 'Account overview.', 'Your licence, computers and access in one place.'],
      licence: ['LICENCE & ACCESS', 'Your licence.', 'Review plan status, competition access and available computer capacity.'],
      'activation-key': ['QUICK ACTIVATION', 'Quick activation.', 'Reveal or rotate the private key used to prepare your Windows stations.'],
      activation: ['PAIR A COMPUTER', 'Connect the app.', 'Approve a waiting LongJumpReplay station without sharing a password or reusable key.'],
      devices: ['COMPUTERS', 'Your computers.', 'See activation method, recent activity and the slots used by each station.'],
      billing: ['BILLING', 'Billing and invoices.', 'Manage subscription payments and keep your purchase documents together.'],
      help: ['HELP & SECURITY', 'Help & security.', 'Installation, support and practical guidance for keeping access safe.']
    },
    cs: {
      overview: ['PŘEHLED ÚČTU', 'Přehled účtu.', 'Licence, počítače a přístup na jednom místě.'],
      licence: ['LICENCE A PŘÍSTUP', 'Vaše licence.', 'Zkontrolujte stav plánu, závodní přístup a kapacitu počítačů.'],
      'activation-key': ['RYCHLÁ AKTIVACE', 'Rychlá aktivace.', 'Zobrazte nebo obnovte soukromý klíč pro přípravu stanic Windows.'],
      activation: ['SPÁROVAT POČÍTAČ', 'Propojte aplikaci.', 'Schvalte čekající stanici LongJumpReplay bez sdílení hesla nebo opakovaně použitelného klíče.'],
      devices: ['POČÍTAČE', 'Vaše počítače.', 'Způsob aktivace, poslední aktivita a místa využitá jednotlivými stanicemi.'],
      billing: ['PLATBY', 'Platby a faktury.', 'Spravujte platby předplatného a mějte doklady o nákupu pohromadě.'],
      help: ['POMOC A ZABEZPEČENÍ', 'Pomoc a zabezpečení.', 'Instalace, podpora a praktické rady pro bezpečný přístup.']
    }
  };
  const renderDashboardRoute = (hasActiveLicence) => {
    const route = dashboardRoutes.has(dashboardRoute) ? dashboardRoute : 'overview';
    const [eyebrow, title, description] = routeCopy[state.lang][route];
    $('#dashboard-route-eyebrow').textContent = `LONGJUMPREPLAY / ${eyebrow}`;
    $('#dashboard-title').textContent = title;
    $('#dashboard-route-description').textContent = description;
    document.title = `${title.replace(/\.$/, '')} — LongJumpReplay account`;
    document.querySelector('link[rel="canonical"]')?.setAttribute('href', `https://account.tomaspisar.cz/dashboard/${route}`);
    document.querySelectorAll('[data-dashboard-link]').forEach((link) => {
      if (link.dataset.dashboardLink === route) link.setAttribute('aria-current', 'page');
      else link.removeAttribute('aria-current');
    });
    document.querySelectorAll('[data-dashboard-route]').forEach((section) => {
      const available = section.id !== 'additional-computers' || section.dataset.available === 'true';
      section.hidden = section.dataset.dashboardRoute !== route || !available;
    });
    $('#activation-key-card').hidden = !hasActiveLicence;
    $('#activation-key-unavailable').hidden = hasActiveLicence;
  };
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
        $('#email-step').hidden = true;
        $('#code-field').hidden = false;
        $('#change-email').hidden = false;
        $('#resend-code').hidden = false;
        $('#login-submit').textContent = state.lang === 'cs' ? 'Ověřit kód' : 'Verify code';
        setStatus(t('sent'), '#login-status');
        $('#code').focus();
      } catch (error) { setStatus(error.message, '#login-status'); }
      finally { setLoginBusy(false); }
    };

    const changeEmail = () => {
      state.codeSent = false;
      $('#email-step').hidden = false;
      $('#code-field').hidden = true;
      $('#change-email').hidden = true;
      $('#resend-code').hidden = true;
      $('#login-submit').textContent = state.lang === 'cs' ? 'PokraÄovat' : 'Continue';
      $('#code').value = '';
      setStatus('', '#login-status');
      $('#email').focus();
    };

    const resendCode = () => {
      if (!state.email) return changeEmail();
      $('#email').value = state.email;
      requestCode();
    };

    const verifyCode = async () => {
      const code = $('#code').value.trim();
      if (!/^\d{6}$/.test(code)) { setStatus(t('invalidCode'), '#login-status'); return; }
      setStatus(t('checking'), '#login-status');
      setLoginBusy(true);
      try {
        await api('/api/portal/verify-code', { method: 'POST', body: JSON.stringify({ email: state.email, code }) });
        setStatus(t('verified'), '#login-status');
        window.setTimeout(() => window.location.replace('/dashboard/overview'), 180);
      } catch (error) {
        const expired = error.status === 410 || String(error.code || '').toLowerCase().includes('expired');
        setStatus(expired ? t('expiredCode') : error.message, '#login-status');
        $('#code').setAttribute('aria-invalid', 'true');
      }
      finally { setLoginBusy(false); }
    };

    $('#change-email').addEventListener('click', changeEmail);
    $('#resend-code').addEventListener('click', resendCode);
    $('#code').addEventListener('input', () => $('#code').removeAttribute('aria-invalid'));
    form.addEventListener('submit', (event) => { event.preventDefault(); state.codeSent ? verifyCode() : requestCode(); });
    api('/api/portal/account').then(() => window.location.replace('/dashboard/overview')).catch(() => $('#email').focus());
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
    $('#devices-list').innerHTML = devices.length ? `<table class="data-table device-table"><thead><tr><th>${t('computer')}</th><th>${t('method')}</th><th>${t('activated')}</th><th>${t('lastActive')}</th><th>${t('status')}</th><th>${t('actions')}</th></tr></thead><tbody>${devices.map((device) => {
      const { entitledActive, canDeactivate, canDelete } = deriveDevicePortalState(device, activeLicenceIds);
      const method = device.activation_method === 'key' ? t('keyMethod') : t('emailMethod');
      const status = entitledActive
        ? t('statusActive')
        : canDeactivate
          ? t('statusLicenceInactive')
          : t('statusDeactivated');
      const deviceAction = canDeactivate
        ? `<button class="small-button" type="button" data-deactivate="${escapeHtml(device.id)}">${t('deactivate')}</button>`
        : canDelete
          ? `<button class="small-button danger" type="button" data-delete-device="${escapeHtml(device.id)}">${t('delete')}</button>`
          : '';
      return `<tr><td><strong>${escapeHtml(device.device_name || 'LongJumpReplay computer')}</strong></td><td>${method}</td><td>${formatDateTime(device.activated_at)}</td><td>${formatDateTime(device.last_verified_at)}</td><td><span class="badge ${entitledActive ? '' : 'warn'}">${status}</span></td><td><div class="row-actions"><button class="small-button" type="button" data-details="${escapeHtml(device.id)}">${t('details')}</button>${deviceAction}</div></td></tr>`;
    }).join('')}</tbody></table>` : `<div class="empty">${t('noDevices')}</div>`;
  };

  const hideActivationKey = () => {
    state.keyVisible = false; state.keyValue = '';
    if ($('#activation-key-value')) $('#activation-key-value').textContent = '••••-••••-••••';
    if ($('#activation-key-reveal')) $('#activation-key-reveal').textContent = state.lang === 'cs' ? 'Zobrazit klíč' : 'Show key';
  };

  const renderActivationKeys = async (data) => {
    const licences = (data.licenses || []).filter((licence) => licence.status === 'active');
    const select = $('#licence-key-select');
    if (!select || !licences.length) return;
    const previous = state.keyLicenceId;
    select.innerHTML = licences.map((licence) => `<option value="${escapeHtml(licence.id)}">${licence.type === 'subscription' ? t('subscription') : t('lifetime')}</option>`).join('');
    state.keyLicenceId = licences.some((licence) => licence.id === previous) ? previous : licences[0].id;
    select.value = state.keyLicenceId;
    hideActivationKey();
    if (!state.ensuredKeys.has(state.keyLicenceId)) {
      try {
        await api('/api/portal/activation-key/ensure', { method: 'POST', body: JSON.stringify({ license_id: state.keyLicenceId }) });
        state.ensuredKeys.add(state.keyLicenceId);
      } catch (error) { setStatus(error.message); }
    }
  };

  const renderInvoices = (invoices) => {
    $('#invoices').innerHTML = invoices.length ? `<table class="data-table"><thead><tr><th>${t('invoice')}</th><th>${t('date')}</th><th>${t('amount')}</th><th>${t('status')}</th></tr></thead><tbody>${invoices.map((invoice) => `<tr><td>${invoice.hosted_invoice_url ? `<a href="${escapeHtml(invoice.hosted_invoice_url)}" target="_blank" rel="noopener">${escapeHtml(invoice.id)}</a>` : escapeHtml(invoice.id)}</td><td>${formatDate(invoice.created)}</td><td>${formatMoney(invoice.amount_paid, invoice.currency)}</td><td>${escapeHtml(invoice.status || '—')}</td></tr>`).join('')}</tbody></table>` : `<div class="empty">${t('noInvoices')}</div>`;
  };

  const renderAdditionalComputers = (offers) => {
    const section = $('#additional-computers');
    const card = $('#additional-computers-card');
    const offer = (offers || [])[0];
    section.dataset.available = offer && offer.remaining > 0 ? 'true' : 'false';
    if (!offer || offer.remaining < 1) { section.hidden = true; return; }
    const money = (amount) => new Intl.NumberFormat(state.lang === 'cs' ? 'cs-CZ' : 'en-GB', { style: 'currency', currency: 'CZK', maximumFractionDigits: 0 }).format(amount);
    const options = Array.from({ length: offer.remaining }, (_, index) => `<option value="${index + 1}">${index + 1}</option>`).join('');
    const breakdown = offer.breakdown.map((item) => `<span><span>${t('computer')} ${item.computer}</span><strong>${money(item.amount_czk)}</strong></span>`).join('');
    card.innerHTML = `<div><span class="badge">${t('lifetime')}</span><h3>${t('additionalTitle')}</h3><p>${offer.current_max_devices === 10 ? '10 / 10' : `${offer.current_max_devices} / 10 ${t('usedOf')}`}. ${t('addUpTo')} ${offer.remaining}.</p><div class="addon-breakdown">${breakdown}</div></div><div class="addon-purchase-box"><label for="additional-computers-quantity">${t('quantity')}</label><select id="additional-computers-quantity">${options}</select><div class="addon-total"><span>Total</span><strong id="additional-computers-total">${money(offer.breakdown[0].amount_czk)}</strong></div><button id="additional-computers-purchase" class="button button-primary button-full" type="button">${t('purchase')}</button></div>`;
    const quantity = $('#additional-computers-quantity');
    const total = $('#additional-computers-total');
    const update = () => { const count = Number(quantity.value); total.textContent = money(offer.breakdown.slice(0, count).reduce((sum, item) => sum + item.amount_czk, 0)); };
    quantity.addEventListener('change', update);
    $('#additional-computers-purchase').addEventListener('click', async () => {
      const button = $('#additional-computers-purchase'); button.disabled = true; setStatus(t('sending'));
      try { const result = await api('/api/portal/additional-computers', { method: 'POST', body: JSON.stringify({ license_id: offer.license_id, quantity: Number(quantity.value) }) }); window.location.href = result.url; }
      catch (error) { setStatus(error.message); button.disabled = false; await loadDashboard(); }
    });
  };

  const pairingLicenceOrder = (pairing) => (state.account?.licenses || [])
    .filter((licence) => licence.status === 'active')
    .map((licence) => {
      const devices = (state.account?.devices || []).filter((device) => device.license_id === licence.id && device.status === 'active');
      const sameMachine = devices.some((device) => device.machine_id && device.machine_id === pairing?.machine_id);
      const available = sameMachine || devices.length < Number(licence.max_devices || 0);
      return { licence, devices, sameMachine, available };
    })
    .sort((a, b) => Number(b.sameMachine) - Number(a.sameMachine) || Number(b.available) - Number(a.available) || (a.licence.type === 'lifetime' ? -1 : 1));

  const renderPairing = (pairing) => {
    const review = $('#pairing-review');
    const select = $('#pairing-licence');
    const capacity = $('#pairing-capacity');
    if (!review || !select || !pairing) return;
    const choices = pairingLicenceOrder(pairing);
    const available = choices.filter((choice) => choice.available);
    select.innerHTML = choices.map(({ licence, devices, sameMachine, available: canUse }) => {
      const name = licence.type === 'subscription' ? t('subscription') : t('lifetime');
      const detail = sameMachine ? ` · ${t('pairingSameMachine')}` : ` · ${Math.max(0, Number(licence.max_devices || 0) - devices.length)} ${t('pairingAvailable')}`;
      return `<option value="${escapeHtml(licence.id)}" ${canUse ? '' : 'disabled'}>${escapeHtml(name + detail)}</option>`;
    }).join('');
    const first = available[0] || choices[0];
    if (first) select.value = first.licence.id;
    $('#pairing-device-name').textContent = pairing.device_name || 'LongJumpReplay computer';
    $('#pairing-device-details').textContent = [pairing.app_version, pairing.os_version, pairing.architecture].filter(Boolean).join(' · ') || '—';
    capacity.textContent = available.length ? t('pairingFound') : t('pairingNoCapacity');
    capacity.dataset.state = available.length ? 'ready' : 'warning';
    $('#pairing-confirm').disabled = !available.length;
    review.hidden = false;
  };

  const inspectPairing = async (value) => {
    const input = String(value || $('#pairing-code')?.value || '').trim();
    const payload = /^\d{6}$/.test(input) ? { pairing_code: input } : { pairing_token: input };
    if (!payload.pairing_code && !payload.pairing_token) { setStatus(t('pairingRequired')); return; }
    const find = $('#pairing-find');
    if (find) { find.disabled = true; find.setAttribute('aria-busy', 'true'); }
    setStatus(t('sending'));
    try {
      const data = await api('/api/portal/pairing/inspect', { method: 'POST', body: JSON.stringify(payload) });
      state.pairing = data.pairing;
      renderPairing(state.pairing);
      setStatus(t('pairingFound'));
    } catch (error) {
      state.pairing = null;
      $('#pairing-review')?.setAttribute('hidden', '');
      setStatus(error.status === 410 ? t('pairingExpired') : error.message);
    } finally {
      if (find) { find.disabled = false; find.removeAttribute('aria-busy'); }
    }
  };

  const confirmPairing = async () => {
    if (!state.pairing) return;
    const licenseId = $('#pairing-licence')?.value;
    if (!licenseId) return;
    const button = $('#pairing-confirm');
    button.disabled = true;
    button.setAttribute('aria-busy', 'true');
    setStatus(t('sending'));
    try {
      await api('/api/portal/pairing/confirm', { method: 'POST', body: JSON.stringify({ pairing_id: state.pairing.id, license_id: licenseId }) });
      setStatus(t('pairingApproved'));
      renderPairing({ ...state.pairing });
      await loadDashboard();
    } catch (error) { setStatus(error.message); button.disabled = false; }
    finally { button.removeAttribute('aria-busy'); }
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
    $('#billing-button').hidden = !data.billing?.customer_portal_available;
    document.querySelectorAll('[data-open-billing]').forEach((button) => { button.hidden = !data.billing?.customer_portal_available; });
    $('#device-count').textContent = `${activeDevices.length} ${state.lang === 'cs' ? 'aktivní' : 'active'} · ${Math.max(0, totalSlots - activeDevices.length)} ${t('available')}`;
    renderLicenceCards(licences);
    renderDevices(devices, activeLicenceIds);
    renderActivationKeys(data);
    renderInvoices(data.invoices || []);
    renderAdditionalComputers(data.additional_computers || []);
    renderDashboardRoute(hasActiveLicence);
    if (state.pairing) renderPairing(state.pairing);
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

  const deleteDevice = async (deviceId) => {
    const prompt = state.lang === 'cs' ? 'Trvale smazat deaktivovaný počítač a jeho historii aktivity?' : 'Permanently delete this deactivated computer and its activity history?';
    if (!window.confirm(prompt)) return;
    try {
      await api('/api/portal/delete-device', { method: 'POST', body: JSON.stringify({ device_id: deviceId }) });
      await loadDashboard();
    } catch (error) { setStatus(error.message); }
  };

  const showDeviceDetails = async (deviceId) => {
    try {
      const data = await api(`/api/portal/device-details?device_id=${encodeURIComponent(deviceId)}`);
      const device = data.device;
      $('#device-details-title').textContent = device.device_name || 'LongJumpReplay computer';
      $('#device-details-content').innerHTML = `<dl class="device-facts"><div><dt>${t('status')}</dt><dd>${escapeHtml(device.status)}</dd></div><div><dt>${t('method')}</dt><dd>${device.activation_method === 'key' ? t('keyMethod') : t('emailMethod')}</dd></div><div><dt>${t('activated')}</dt><dd>${formatDateTime(device.activated_at)}</dd></div><div><dt>${t('lastActive')}</dt><dd>${formatDateTime(device.last_verified_at)}</dd></div></dl><details class="advanced-details"><summary>${state.lang === 'cs' ? 'Zobrazit technické údaje a aktivitu' : 'Show technical details and activity'}</summary><dl class="device-facts"><div><dt>App version</dt><dd>${escapeHtml(device.app_version || '—')}</dd></div><div><dt>Windows</dt><dd>${escapeHtml(device.os_version || '—')}</dd></div><div><dt>Architecture</dt><dd>${escapeHtml(device.architecture || '—')}</dd></div><div><dt>Device ID</dt><dd><code>${escapeHtml(device.id)}</code></dd></div><div><dt>Machine ID</dt><dd><code>${escapeHtml(device.machine_id)}</code></dd></div><div><dt>Key generation</dt><dd>${escapeHtml(device.activation_key_generation || '—')}</dd></div></dl><div class="activity-list">${(data.activity || []).map((item) => `<article><strong>${escapeHtml(item.event_type)}</strong><span>${formatDateTime(item.created_at)}</span><code>${escapeHtml(item.ip_address || '—')}</code><span>${escapeHtml(item.country || '—')}</span></article>`).join('') || `<p class="muted">${state.lang === 'cs' ? 'Žádná historie aktivity.' : 'No activity history.'}</p>`}</div></details>`;
      $('#device-details-dialog').showModal();
    } catch (error) { setStatus(error.message); }
  };

  const fetchActivationKey = async () => {
    if (!state.ensuredKeys.has(state.keyLicenceId)) {
      await api('/api/portal/activation-key/ensure', { method: 'POST', body: JSON.stringify({ license_id: state.keyLicenceId }) });
      state.ensuredKeys.add(state.keyLicenceId);
    }
    return api('/api/portal/activation-key/reveal', { method: 'POST', body: JSON.stringify({ license_id: state.keyLicenceId }) });
  };

  const revealActivationKey = async () => {
    if (state.keyVisible) { hideActivationKey(); return; }
    try {
      const data = await fetchActivationKey();
      state.keyVisible = true; state.keyValue = data.key;
      $('#activation-key-value').textContent = data.key;
      $('#activation-key-reveal').textContent = state.lang === 'cs' ? 'Skrýt klíč' : 'Hide key';
    } catch (error) { setStatus(error.message); }
  };

  const writeClipboard = async (value) => {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(value);
      return;
    }
    const field = document.createElement('textarea');
    field.value = value;
    field.setAttribute('readonly', '');
    field.style.position = 'fixed';
    field.style.opacity = '0';
    document.body.appendChild(field);
    field.select();
    const copied = document.execCommand('copy');
    field.remove();
    if (!copied) throw new Error('copy failed');
  };

  const copyActivationKey = async () => {
    const button = $('#activation-key-copy');
    button.disabled = true;
    button.setAttribute('aria-busy', 'true');
    button.textContent = state.lang === 'cs' ? 'Kopíruji…' : 'Copying…';
    try {
      let value = state.keyValue;
      if (!value) {
        const data = await fetchActivationKey();
        value = data.key;
      }
      await writeClipboard(value);
      setStatus(state.lang === 'cs' ? 'Zkopírováno' : 'Copied');
    } catch {
      setStatus(state.lang === 'cs' ? 'Klíč se nepodařilo zkopírovat.' : 'The key could not be copied.');
    } finally {
      button.disabled = false;
      button.removeAttribute('aria-busy');
      button.textContent = state.lang === 'cs' ? 'Kopírovat klíč' : 'Copy key';
    }
  };

  const regenerateActivationKey = async () => {
    const keyed = (state.account?.devices || []).filter((device) => device.license_id === state.keyLicenceId && device.status === 'active' && device.activation_method === 'key').length;
    const prompt = state.lang === 'cs' ? `Vygenerovat nový klíč? Odpojí se ${keyed} počítačů aktivovaných klíčem. Počítače aktivované e-mailem zůstanou připojené.` : `Generate a new key? This disconnects ${keyed} key-activated computer(s). Email-activated computers stay connected.`;
    if (!window.confirm(prompt)) return;
    try {
      const data = await api('/api/portal/activation-key/regenerate', { method: 'POST', body: JSON.stringify({ license_id: state.keyLicenceId }) });
      state.keyVisible = true; state.keyValue = data.key;
      $('#activation-key-value').textContent = data.key;
      $('#activation-key-reveal').textContent = state.lang === 'cs' ? 'Skrýt klíč' : 'Hide key';
      setStatus(state.lang === 'cs' ? `Nový klíč je připraven. Odpojeno počítačů: ${data.disconnected_devices}.` : `New key ready. Disconnected computers: ${data.disconnected_devices}.`);
      if (state.account) state.account.devices = state.account.devices.map((device) => device.license_id === state.keyLicenceId && device.activation_method === 'key' ? { ...device, status: 'deactivated' } : device);
      renderDevices(state.account.devices, new Set((state.account.licenses || []).filter((licence) => licence.status === 'active').map((licence) => licence.id)));
    } catch (error) { setStatus(error.message); }
  };

  const signOut = async () => {
    try { await api('/api/portal/logout', { method: 'POST', body: '{}' }); }
    finally { window.location.replace('/login'); }
  };

  const openBilling = async () => {
    setStatus(t('sending'));
    try { const data = await api('/api/portal/billing', { method: 'POST', body: '{}' }); window.location.href = data.url; }
    catch (error) { setStatus(error.message); }
  };

  const initDashboard = () => {
    renderDashboardRoute(false);
    document.addEventListener('click', (event) => {
      const button = event.target.closest('[data-deactivate]');
      if (button) deactivate(button.dataset.deactivate);
      const deleteButton = event.target.closest('[data-delete-device]');
      if (deleteButton) deleteDevice(deleteButton.dataset.deleteDevice);
      const detailsButton = event.target.closest('[data-details]');
      if (detailsButton) showDeviceDetails(detailsButton.dataset.details);
    });
    $('#billing-button')?.addEventListener('click', openBilling);
    document.querySelectorAll('[data-open-billing]').forEach((button) => button.addEventListener('click', openBilling));
    $('#logout-button')?.addEventListener('click', signOut);
    $('#security-logout-button')?.addEventListener('click', signOut);
    $('#device-details-close')?.addEventListener('click', () => $('#device-details-dialog').close());
    $('#activation-key-reveal')?.addEventListener('click', revealActivationKey);
    $('#activation-key-copy')?.addEventListener('click', copyActivationKey);
    $('#activation-key-regenerate')?.addEventListener('click', regenerateActivationKey);
    $('#pairing-form')?.addEventListener('submit', (event) => { event.preventDefault(); inspectPairing(); });
    $('#pairing-confirm')?.addEventListener('click', confirmPairing);
    $('#licence-key-select')?.addEventListener('change', async (event) => {
      state.keyLicenceId = event.target.value; hideActivationKey();
      if (!state.ensuredKeys.has(state.keyLicenceId)) {
        try { await api('/api/portal/activation-key/ensure', { method: 'POST', body: JSON.stringify({ license_id: state.keyLicenceId }) }); state.ensuredKeys.add(state.keyLicenceId); }
        catch (error) { setStatus(error.message); }
      }
    });
    loadDashboard().then(() => {
      if (dashboardRoute === 'activation') {
        const token = new URLSearchParams(window.location.search).get('pair');
        if (token) inspectPairing(token);
      }
    });
  };

  document.querySelector('[data-lang-toggle]')?.addEventListener('click', () => window.setTimeout(() => {
    state.lang = document.documentElement.lang === 'cs' ? 'cs' : 'en';
    if (state.account && page === 'dashboard') renderDashboard(state.account);
    if (state.pairing && page === 'dashboard') renderPairing(state.pairing);
    if (state.codeSent && page === 'login') $('#login-submit').textContent = state.lang === 'cs' ? 'Přihlásit' : 'Sign in';
  }, 0));

  if (page === 'login') initLogin();
  if (page === 'dashboard') initDashboard();
})();
