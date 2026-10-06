(() => {
  const API = 'https://api.tomaspisar.cz';
  const { deriveDashboardEntitlement, deriveDevicePortalState } = window.LJR_ACCOUNT_STATE;
  const page = document.body.dataset.portalPage;
  const productParams = new URLSearchParams(window.location.search);
  const playerProduct = productParams.get('product') === 'economysuite';
  const loginProduct = playerProduct ? 'economysuite' : 'longjumpreplay';
  const playerNext = /^\/economysuite\/(overview|statistics|progress|appearance|store|purchases|settings|pair)$/.test(productParams.get('next') || '') ? productParams.get('next') : '/economysuite/overview';
  if (page === 'login') {
    const destination = document.querySelector('#form-title');
    const productCopy = playerProduct
      ? { en: 'Pantheon / EconomySuite', cs: 'Pantheon / EconomySuite' }
      : { en: 'LongJumpReplay', cs: 'LongJumpReplay' };
    if (destination) {
      destination.dataset.en = productCopy.en;
      destination.dataset.cs = productCopy.cs;
      destination.textContent = document.documentElement.lang === 'cs' ? productCopy.cs : productCopy.en;
    }
    document.querySelectorAll('[data-login-product]').forEach((link) => {
      if (link.dataset.loginProduct === loginProduct) link.setAttribute('aria-current', 'page');
      else link.removeAttribute('aria-current');
    });
  }
  if (playerProduct && ['login', 'register'].includes(page)) {
    document.title = 'Pantheon / EconomySuite — Account';
    const eyebrow = document.querySelector('.account-intro .eyebrow span[data-en]');
    if (eyebrow) { eyebrow.dataset.en = 'PANTHEON / PLAYER ACCOUNT'; eyebrow.dataset.cs = 'PANTHEON / HRÁČSKÝ ÚČET'; eyebrow.textContent = eyebrow.dataset.en; }
    document.querySelectorAll('a[href="/register"],a[href="/login"]').forEach(a => { a.href = `${a.getAttribute('href')}?product=economysuite&next=${encodeURIComponent(playerNext)}`; });
    const title = document.querySelector('#login-title') || document.querySelector('#register-title');
    if (title) { title.dataset.en = 'Your Pantheon player account.'; title.dataset.cs = 'Tvůj hráčský účet na Pantheonu.'; title.textContent = document.documentElement.lang === 'cs' ? title.dataset.cs : title.dataset.en; }
    const intro = document.querySelector('.account-intro .hero-lede');
    if (intro) { intro.dataset.en = page === 'register' ? 'Create an account with your email and password, then pair your Minecraft player in-game. Your progress and balances stay private.' : 'Sign in to see your Pantheon stats, progression, appearances and purchases. Pair your Minecraft player using /web link.'; intro.dataset.cs = page === 'register' ? 'Vytvoř si účet pomocí e-mailu a hesla a potom propoj svého Minecraft hráče ve hře. Postup a zůstatky jsou soukromé.' : 'Přihlas se ke statistikám, postupu, vzhledu a nákupům na Pantheonu. Minecraft hráče propoj pomocí /web link.'; intro.textContent = document.documentElement.lang === 'cs' ? intro.dataset.cs : intro.dataset.en; }
    document.querySelectorAll('label[for^="register-first"],label[for^="register-last"],label[for^="register-club"],#register-first-name,#register-last-name,#register-club-name,label[for^="migration-first"],label[for^="migration-last"],label[for^="migration-club"],#migration-first-name,#migration-last-name,#migration-club-name').forEach(el => { el.hidden = true; el.required = false; });
  }
  const dashboardRoute = page === 'dashboard' ? (window.location.pathname.split('/').filter(Boolean)[1] || 'overview') : '';
  const dashboardRoutes = new Set(['overview', 'licence', 'activation-key', 'activation', 'devices', 'billing', 'profile', 'help']);
  const state = { lang: document.documentElement.lang === 'cs' ? 'cs' : 'en', email: '', codeSent: false, account: null,
    keyVisible: false, keyValue: '', keyLicenceId: '', ensuredKeys: new Set(), pairing: null };
  const $ = (selector) => document.querySelector(selector);
  const PENDING_PAIRING_KEY = 'ljr_pending_pairing_v1';
  const pairingTokenFromLocation = () => {
    const fragment = new URLSearchParams(window.location.hash.replace(/^#/, '')).get('pair');
    const query = new URLSearchParams(window.location.search).get('pair');
    const token = String(fragment || query || '').trim();
    return /^[A-Za-z0-9_-]{20,256}$/.test(token) ? token : '';
  };
  const readPendingPairing = () => {
    try {
      const stored = JSON.parse(sessionStorage.getItem(PENDING_PAIRING_KEY) || 'null');
      if (!stored?.token || Date.now() - Number(stored.savedAt || 0) > 15 * 60 * 1000) {
        sessionStorage.removeItem(PENDING_PAIRING_KEY);
        return '';
      }
      return String(stored.token);
    } catch { return ''; }
  };
  const storePendingPairing = (token) => {
    try { sessionStorage.setItem(PENDING_PAIRING_KEY, JSON.stringify({ token, savedAt: Date.now() })); } catch { /* best effort */ }
  };
  const clearPendingPairing = () => {
    try { sessionStorage.removeItem(PENDING_PAIRING_KEY); } catch { /* best effort */ }
  };
  const stripPairingFromLocation = () => {
    const url = new URL(window.location.href);
    url.searchParams.delete('pair');
    url.hash = '';
    window.history.replaceState({}, document.title, `${url.pathname}${url.search}`);
  };
  const capturePairingFromLocation = () => {
    const token = pairingTokenFromLocation();
    if (token) { storePendingPairing(token); stripPairingFromLocation(); }
    return token || readPendingPairing();
  };
  const copy = {
    en: {
      passwordLength: 'Use a password with at least 12 characters.', signingIn: 'Signing inâ€¦', resetSent: 'If the account can reset a password, a code is on the way. It is valid for 10 minutes.',
      expiredCode: 'This code has expired. Request a new one.', verified: 'Verified. Opening your account…',
      sending: 'Sending code…', checking: 'Checking code…', sent: 'A code is on the way. It is valid for 10 minutes.',
      invalidEmail: 'Enter a valid email address.', invalidCode: 'Enter the six-digit code from your email.',
      genericError: 'We could not complete that request. Check your connection and try again.', noDevices: 'No activated computers.',
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
      profileSaved: 'Profile saved.', passwordSaved: 'Password saved.', copied: 'Copied to clipboard.', keyRegenerated: 'New activation key is ready.', deviceDeactivated: 'Computer deactivated.', deviceDeleted: 'Computer removed.',
      pairingRequired: 'Enter the six-digit code shown by LongJumpReplay or open the QR link.', pairingFound: 'Computer found. Choose an active licence with an available slot.', pairingApproved: 'Approved. The app can finish activation now.', pairingNoCapacity: 'No active licence has an available computer slot.', pairingExpired: 'This pairing request is missing or expired.', pairingSameMachine: 'Already used by this computer', pairingAvailable: 'available slot', pairingApprove: 'Approve and activate'
    },
    cs: {
      passwordLength: 'PouÅ¾ijte heslo dlouhÃ© alespoÅˆ 12 znakÅ¯.', signingIn: 'PÅ™ihlaÅ¡ujiâ€¦', resetSent: 'Pokud lze heslo obnovit, kÃ³d je na cestÄ›. PlatÃ­ 10 minut.',
      expiredCode: 'Kód vypršel. Požádejte o nový.', verified: 'Ověřeno. Otevírám účet…',
      sending: 'Odesílám kód…', checking: 'Ověřuji kód…', sent: 'Kód je na cestě. Platí 10 minut.',
      invalidEmail: 'Zadejte platnou e-mailovou adresu.', invalidCode: 'Zadejte šestimístný kód z e-mailu.',
      genericError: 'Požadavek se nepodařilo dokončit. Zkontrolujte připojení a zkuste to znovu.', noDevices: 'Žádné aktivované počítače.',
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
      profileSaved: 'Profil byl uložen.', passwordSaved: 'Heslo bylo uloženo.', copied: 'Zkopírováno do schránky.', keyRegenerated: 'Nový aktivační klíč je připraven.', deviceDeactivated: 'Počítač byl deaktivován.', deviceDeleted: 'Počítač byl odstraněn.',
      pairingRequired: 'Zadejte šestimístný kód z LongJumpReplay nebo otevřete QR odkaz.', pairingFound: 'Počítač nalezen. Vyberte aktivní licenci s volným místem.', pairingApproved: 'Schváleno. Aplikace nyní dokončí aktivaci.', pairingNoCapacity: 'Žádná aktivní licence nemá volné místo pro počítač.', pairingExpired: 'Párování chybí nebo vypršelo.', pairingSameMachine: 'Tento počítač je již použit', pairingAvailable: 'volné místo', pairingApprove: 'Schválit a aktivovat'
    }
  };

  class ApiError extends Error {
    constructor(message, status, code) { super(message); this.status = status; this.code = code; }
  }

  copy.en.passwordLength = 'Use 12-128 characters, including a letter, number and symbol.';
  copy.en.passwordMismatch = 'The passwords do not match.';
  copy.en.profileRequired = 'Enter your first name and surname.';
  copy.en.passwordRules = 'Use 12-128 characters, including a letter, number and symbol.';
  copy.cs.passwordLength = 'Pouzijte 12-128 znaku vcetne pismene, cisla a symbolu.';
  copy.cs.passwordMismatch = 'Hesla se neshoduji.';
  copy.cs.profileRequired = 'Zadejte jmeno a prijmeni.';
  copy.cs.passwordRules = 'Pouzijte 12-128 znaku vcetne pismene, cisla a symbolu.';
  const t = (key) => copy[state.lang][key] || copy.en[key] || key;
  const strongPassword = (value) => Array.from(value).length >= 12 && Array.from(value).length <= 128
    && /\p{L}/u.test(value) && /\p{N}/u.test(value) && /[\p{P}\p{S}]/u.test(value);
  const routeCopy = {
    en: {
      overview: ['ACCOUNT OVERVIEW', 'Your LongJumpReplay access.', 'Check your licence and choose what to do next.'],
      licence: ['LICENCE & ACCESS', 'Your licence.', 'Review plan status, competition access and available computer capacity.'],
      'activation-key': ['QUICK ACTIVATION', 'Quick activation.', 'Reveal or rotate the private key used to prepare your Windows stations.'],
      activation: ['PAIR A COMPUTER', 'Connect the app.', 'Approve a waiting LongJumpReplay station without sharing a password or reusable key.'],
      devices: ['COMPUTERS', 'Your computers.', 'See activation method, recent activity and the slots used by each station.'],
      billing: ['BILLING', 'Billing and invoices.', 'Manage subscription payments and keep your purchase documents together.'],
      profile: ['PROFILE', 'Your profile.', 'Update your name, club and sign-in password.'],
      help: ['HELP & SECURITY', 'Help & security.', 'Installation, support and practical guidance for keeping access safe.']
    },
    cs: {
      overview: ['PŘEHLED ÚČTU', 'Váš přístup k LongJumpReplay.', 'Zkontrolujte licenci a vyberte další krok.'],
      licence: ['LICENCE A PŘÍSTUP', 'Vaše licence.', 'Zkontrolujte stav plánu, závodní přístup a kapacitu počítačů.'],
      'activation-key': ['RYCHLÁ AKTIVACE', 'Rychlá aktivace.', 'Zobrazte nebo obnovte soukromý klíč pro přípravu stanic Windows.'],
      activation: ['SPÁROVAT POČÍTAČ', 'Propojte aplikaci.', 'Schvalte čekající stanici LongJumpReplay bez sdílení hesla nebo opakovaně použitelného klíče.'],
      devices: ['POČÍTAČE', 'Vaše počítače.', 'Způsob aktivace, poslední aktivita a místa využitá jednotlivými stanicemi.'],
      billing: ['PLATBY', 'Platby a faktury.', 'Spravujte platby předplatného a mějte doklady o nákupu pohromadě.'],
      profile: ['PROFIL', 'Váš profil.', 'Upravte své jméno, klub a přihlašovací heslo.'],
      help: ['POMOC A ZABEZPEČENÍ', 'Pomoc a zabezpečení.', 'Instalace, podpora a praktické rady pro bezpečný přístup.']
    }
  };
  const renderDashboardRoute = (hasActiveLicence) => {
    const route = dashboardRoutes.has(dashboardRoute) ? dashboardRoute : 'overview';
    const [, title] = routeCopy[state.lang][route];
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
  const feedback = window.LJR_FEEDBACK;
  const readableError = (value) => {
    const error = value && typeof value === 'object' ? value : { message: value };
    const code = String(error.code || '').toLowerCase();
    const mapped = {
      not_authenticated: t('sessionExpired'), expired: t('expiredCode'), code_expired: t('expiredCode'),
      invalid_code: t('invalidCode'), license_inactive: state.lang === 'cs' ? 'Tato licence není aktivní.' : 'This licence is not active.',
      no_capacity: state.lang === 'cs' ? 'Licence už nemá volné místo pro další počítač.' : 'This licence has no available computer slot.',
      not_found: state.lang === 'cs' ? 'Požadované údaje nebyly nalezeny. Obnovte stránku a zkuste to znovu.' : 'The requested item was not found. Refresh the page and try again.'
    };
    if (mapped[code]) return mapped[code];
    if (Number(error.status) === 401) return t('sessionExpired');
    if (Number(error.status) === 410) return t('expiredCode');
    if (Number(error.status) === 429) return state.lang === 'cs' ? 'Příliš mnoho pokusů. Chvíli počkejte a zkuste to znovu.' : 'Too many attempts. Wait a moment and try again.';
    if (Number(error.status) >= 500 || /failed to fetch|network|database|sql|stripe api|exception|stack trace|undefined/i.test(String(error.message || ''))) return t('genericError');
    const message = String(error.message || '').trim();
    return message && message.length <= 180 ? message : t('genericError');
  };
  const setStatus = (value, selector = '#account-status', kind = 'info') => {
    const element = $(selector);
    if (!element) return;
    const message = value ? readableError(value) : '';
    feedback?.inline(element, message, message ? kind : 'info');
  };
  const notify = (kind, message, title) => feedback?.toast?.[kind]?.(message, { title });
  const setDashboardRetry = (visible) => { const button = $('#dashboard-refresh'); if (button) button.hidden = !visible; };
  const cookieValue = (name) => document.cookie.split(';').map((part) => part.trim().split('=')).find(([key]) => key === name)?.slice(1).join('=') || '';
  const api = async (path, options = {}) => {
    if (playerProduct && options.body) { try { options.body = JSON.stringify({ ...JSON.parse(options.body), product: 'economysuite' }); } catch { /* existing validation handles malformed bodies */ } }
    const csrf = cookieValue('ljr-portal-csrf');
    const response = await fetch(`${API}${path}`, {
      ...options,
      credentials: 'include',
      headers: { Accept: 'application/json', ...(options.body ? { 'Content-Type': 'application/json' } : {}), ...(csrf ? { 'X-CSRF-Token': decodeURIComponent(csrf) } : {}), ...(options.headers || {}) }
    });
    const raw = await response.text();
    let data = {};
    try {
      const parsed = raw ? JSON.parse(raw) : {};
      data = parsed && typeof parsed === 'object' ? parsed : {};
    } catch { data = { message: raw.trim() }; }
    if (!response.ok) throw new ApiError(data.message || t('genericError'), response.status, data.error || 'error');
    return data;
  };

  const setLoginBusy = (busy) => {
    const button = $('#login-submit');
    if (!button) return;
    button.disabled = busy;
    button.setAttribute('aria-busy', String(busy));
  };

  const initSecureLogin = (form) => {
    const loginState = { mode: 'password', codeSent: false, resetSent: false };
    const redirectAfterAuth = () => {
      if (playerProduct) { window.location.replace(playerNext); return; }
      const pendingPairing = readPendingPairing();
      window.setTimeout(() => window.location.replace(pendingPairing ? `/approve/pairing#pair=${encodeURIComponent(pendingPairing)}` : '/dashboard/overview'), 180);
    };
    const setText = (selector, en, cs) => { const element = $(selector); if (element) element.textContent = state.lang === 'cs' ? cs : en; };
    const setMode = (mode) => {
      loginState.mode = mode;
      loginState.codeSent = false;
      loginState.resetSent = false;
      $('#email-step').hidden = false;
      $('#password-step').hidden = mode !== 'password';
      $('#code-field').hidden = mode !== 'otp';
      $('#migration-step').hidden = true;
      $('#reset-step').hidden = true;
      $('#login-mode-actions').hidden = mode !== 'password';
      $('#login-other-options').hidden = true;
      $('#other-options-toggle').setAttribute('aria-expanded', 'false');
      setText('#other-options-toggle', 'Show other options', 'Zobrazit další možnosti');
      $('#reset-actions').hidden = mode === 'password';
      $('#change-email').hidden = true;
      $('#resend-code').hidden = true;
      $('#password').required = mode === 'password';
      $('#code').required = false;
      setText('#login-submit', mode === 'otp' ? 'Continue' : mode === 'reset' ? 'Send reset code' : 'Sign in', mode === 'otp' ? 'PokraÄovat' : mode === 'reset' ? 'Poslat kÃ³d pro obnovu' : 'PÅ™ihlÃ¡sit se');
      setStatus('', '#login-status');
      (mode === 'password' ? $('#password') : $('#email')).focus();
    };
    const requestOtp = async () => {
      const email = $('#email').value.trim();
      if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) { $('#email').setAttribute('aria-invalid', 'true'); setStatus(t('invalidEmail'), '#login-status', 'error'); return; }
      state.email = email; setStatus(t('sending'), '#login-status'); setLoginBusy(true);
      try {
        await api('/api/portal/request-code', { method: 'POST', body: JSON.stringify({ email }) });
        loginState.codeSent = true; $('#password-step').hidden = true; $('#code-field').hidden = false; $('#change-email').hidden = false; $('#resend-code').hidden = false; $('#login-mode-actions').hidden = true; $('#reset-actions').hidden = false;
        setText('#login-submit', 'Verify code', 'OvÄ›Å™it kÃ³d'); setStatus(t('sent'), '#login-status'); $('#code').focus();
      } catch (error) { setStatus(error, '#login-status', 'error'); } finally { setLoginBusy(false); }
    };
    const verifyOtp = async () => {
      const code = $('#code').value.trim();
      if (!/^\d{6}$/.test(code)) { setStatus(t('invalidCode'), '#login-status', 'error'); $('#code').setAttribute('aria-invalid', 'true'); return; }
      setStatus(t('checking'), '#login-status'); setLoginBusy(true);
      try {
        const result = await api('/api/portal/verify-code', { method: 'POST', body: JSON.stringify({ email: state.email, code }) });
        if (result.password_setup_required) return showMigration(result);
        setStatus(t('verified'), '#login-status'); redirectAfterAuth();
      }
      catch (error) { const expired = error.status === 410 || String(error.code || '').toLowerCase().includes('expired'); setStatus(expired ? t('expiredCode') : error, '#login-status', 'error'); $('#code').setAttribute('aria-invalid', 'true'); }
      finally { setLoginBusy(false); }
    };
    const showMigration = (result) => {
      loginState.mode = 'migration';
      state.setupToken = result.setup_token || '';
      state.email = result.email || state.email;
      $('#email-step').hidden = true; $('#password-step').hidden = true; $('#code-field').hidden = true; $('#migration-step').hidden = false;
      $('#migration-password-fields').hidden = !result.password_required;
      $('#migration-password').required = Boolean(result.password_required);
      $('#migration-password-confirmation').required = Boolean(result.password_required);
      $('#login-mode-actions').hidden = true; $('#reset-actions').hidden = true; $('#change-email').hidden = true; $('#resend-code').hidden = true;
      setText('#login-submit', 'Finish account setup', 'Dokoncit nastaveni uctu');
      setStatus(state.lang === 'cs' ? 'Dokoncete prosim profil a heslo.' : 'Finish your profile and password.', '#login-status');
      (playerProduct ? $('#migration-password') : $('#migration-first-name')).focus();
    };
    const completeMigration = async () => {
      const firstName = $('#migration-first-name').value.trim(); const lastName = $('#migration-last-name').value.trim();
      const clubName = $('#migration-club-name').value.trim(); const password = $('#migration-password').value; const confirmation = $('#migration-password-confirmation').value;
      if (!playerProduct && (!firstName || !lastName)) { setStatus(t('profileRequired'), '#login-status', 'error'); return; }
      if ($('#migration-password-fields').hidden === false && password !== confirmation) { setStatus(t('passwordMismatch'), '#login-status', 'error'); return; }
      if ($('#migration-password-fields').hidden === false && !strongPassword(password)) { setStatus(t('passwordRules'), '#login-status', 'error'); return; }
      setStatus(t('checking'), '#login-status'); setLoginBusy(true);
      try { await api('/api/portal/register/complete', { method: 'POST', body: JSON.stringify({ email: state.email, setup_token: state.setupToken, first_name: firstName, last_name: lastName, club_name: clubName, password, password_confirmation: confirmation }) }); setStatus(state.lang === 'cs' ? 'Účet je připraven. Přesměrovávám na přihlášení…' : 'Your account is ready. Returning to sign in…', '#login-status'); window.setTimeout(() => window.location.replace(playerProduct ? '/login?registered=1&product=economysuite&next=' + encodeURIComponent(playerNext) : '/login?registered=1'), 500); }
      catch (error) { setStatus(error, '#login-status', 'error'); }
      finally { setLoginBusy(false); }
    };
    const loginWithPassword = async () => {
      const email = $('#email').value.trim(); const password = $('#password').value;
      if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) { $('#email').setAttribute('aria-invalid', 'true'); setStatus(t('invalidEmail'), '#login-status', 'error'); return; }
       if (!password) { setStatus(t('passwordLength'), '#login-status', 'error'); return; }
      state.email = email; setStatus(t('signingIn'), '#login-status'); setLoginBusy(true);
      try { const result = await api('/api/portal/password/login', { method: 'POST', body: JSON.stringify({ email, password }) }); setStatus(t('verified'), '#login-status'); if (result.password_setup_required) window.setTimeout(() => window.location.replace(playerProduct ? '/register?mode=migration&product=economysuite' : '/register?mode=migration'), 180); else redirectAfterAuth(); }
      catch (error) { setStatus(error, '#login-status', 'error'); }
      finally { setLoginBusy(false); }
    };
    const requestReset = async () => {
      const email = $('#email').value.trim();
      if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) { $('#email').setAttribute('aria-invalid', 'true'); setStatus(t('invalidEmail'), '#login-status', 'error'); return; }
      state.email = email; setStatus(t('sending'), '#login-status'); setLoginBusy(true);
      try { await api('/api/portal/password/reset/request', { method: 'POST', body: JSON.stringify({ email }) }); loginState.resetSent = true; $('#reset-step').hidden = false; setText('#login-submit', 'Reset password', 'Obnovit heslo'); setStatus(t('resetSent'), '#login-status'); $('#reset-code').focus(); }
      catch (error) { setStatus(error, '#login-status', 'error'); } finally { setLoginBusy(false); }
    };
    const completeReset = async () => {
      const code = $('#reset-code').value.trim(); const newPassword = $('#new-password').value;
      if (!/^\d{6}$/.test(code)) { setStatus(t('invalidCode'), '#login-status', 'error'); return; }
       if (!strongPassword(newPassword)) { setStatus(t('passwordLength'), '#login-status', 'error'); return; }
      setStatus(t('checking'), '#login-status'); setLoginBusy(true);
      try { await api('/api/portal/password/reset', { method: 'POST', body: JSON.stringify({ email: state.email, code, new_password: newPassword }) }); setStatus(t('verified'), '#login-status'); redirectAfterAuth(); }
      catch (error) { setStatus(error, '#login-status', 'error'); } finally { setLoginBusy(false); }
    };
    $('#otp-mode-link').addEventListener('click', () => setMode('otp'));
    $('#forgot-password').addEventListener('click', () => setMode('reset'));
    $('#reset-back').addEventListener('click', () => setMode('password'));
    $('#other-options-toggle').addEventListener('click', () => {
      const options = $('#login-other-options');
      const open = options.hidden;
      options.hidden = !open;
      $('#other-options-toggle').setAttribute('aria-expanded', String(open));
      setText('#other-options-toggle', open ? 'Hide other options' : 'Show other options', open ? 'Skrýt další možnosti' : 'Zobrazit další možnosti');
    });
    $('#change-email').addEventListener('click', () => setMode('otp'));
    $('#resend-code').addEventListener('click', requestOtp);
    $('#code').addEventListener('input', () => $('#code').removeAttribute('aria-invalid'));
    form.addEventListener('submit', (event) => { event.preventDefault(); if (loginState.mode === 'migration') return completeMigration(); if (loginState.mode === 'otp') return loginState.codeSent ? verifyOtp() : requestOtp(); if (loginState.mode === 'reset') return loginState.resetSent ? completeReset() : requestReset(); return loginWithPassword(); });
    setMode('password');
    api('/api/portal/account').then(redirectAfterAuth).catch(() => $('#email').focus());
  };

  const initLogin = () => {
    const form = $('#login-form');
    if (!form) return;
    return initSecureLogin(form);
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
      } catch (error) { setStatus(error, '#account-status', 'error'); }
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
      catch (error) { setStatus(error, '#account-status', 'error'); button.disabled = false; await loadDashboard(); }
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
    if (!payload.pairing_code && !payload.pairing_token) { setStatus(t('pairingRequired'), '#account-status', 'error'); return; }
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
      if (payload.pairing_token) clearPendingPairing();
      setStatus(error.status === 410 ? t('pairingExpired') : error, '#account-status', 'error');
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
      clearPendingPairing();
      setStatus('', '#account-status');
      notify('success', t('pairingApproved'), state.lang === 'cs' ? 'Počítač schválen' : 'Computer approved');
      renderPairing({ ...state.pairing });
      await loadDashboard();
    } catch (error) { setStatus(error, '#account-status', 'error'); button.disabled = false; }
    finally { button.removeAttribute('aria-busy'); }
  };

  const renderPasswordSecurity = (configured) => {
    const tools = $('#password-security-tools');
    const form = $('#password-enroll-form');
    if (!tools || !form) return;
    tools.hidden = false;
    form.dataset.configured = configured ? 'true' : 'false';
    const current = configured
      ? `<label for="current-password">${state.lang === 'cs' ? 'Současné heslo' : 'Current password'}</label><input id="current-password" type="password" autocomplete="current-password" required>`
      : '';
    form.innerHTML = `${current}<label for="enroll-password">${state.lang === 'cs' ? 'Nové heslo' : 'New password'}</label><input id="enroll-password" type="password" minlength="12" autocomplete="new-password" required><label for="confirm-enroll-password">${state.lang === 'cs' ? 'Potvrzení nového hesla' : 'Confirm new password'}</label><input id="confirm-enroll-password" type="password" minlength="12" autocomplete="new-password" required><p class="form-note">${state.lang === 'cs' ? '12–128 znaků včetně písmene, čísla a symbolu.' : '12–128 characters including a letter, number and symbol.'}</p><button class="button button-primary" type="submit">${state.lang === 'cs' ? (configured ? 'Změnit heslo' : 'Vytvořit heslo') : (configured ? 'Change password' : 'Create password')}</button>`;
  };

  const renderDashboard = (data) => {
    state.account = data;
    const licences = data.licenses || [];
    const devices = data.devices || [];
    const {
      activeLicenceIds, activeDevices, totalSlots, primary, hasAnyLicence, hasActiveLicence,
    } = deriveDashboardEntitlement(licences, devices);
    const nextVerification = activeDevices.map((device) => device.last_verified_at || device.activated_at || 0).filter(Boolean).sort((a, b) => a - b)[0];

    if ($('#profile-email')) $('#profile-email').value = data.customer?.email || '';
    if ($('#profile-first-name')) $('#profile-first-name').value = data.profile?.first_name || '';
    if ($('#profile-last-name')) $('#profile-last-name').value = data.profile?.last_name || '';
    if ($('#profile-club-name')) $('#profile-club-name').value = data.profile?.club_name || '';
    $('#summary-licence').textContent = hasActiveLicence
      ? (primary.type === 'subscription' ? t('subscription') : t('lifetime'))
      : t('noActiveLicence');
    $('#summary-licence-note').textContent = primary ? (primary.status === 'active' ? t('statusActive') : t('statusInactive')) : (state.lang === 'cs' ? 'Připraveno k nákupu' : 'Ready when you purchase');
    $('#summary-devices').textContent = `${activeDevices.length} / ${totalSlots}`;
    $('#summary-verification').textContent = nextVerification ? formatDate(nextVerification + (30 * 86400)) : t('verificationReady');
    const freeSlots = Math.max(0, totalSlots - activeDevices.length);
    const nextStep = $('#overview-next-step');
    const primaryLink = $('#overview-primary-link');
    const overviewTitle = $('#overview-title');
    if (!hasActiveLicence) {
      overviewTitle.textContent = state.lang === 'cs' ? 'K připojení počítače potřebujete licenci.' : 'A licence is needed to connect a computer.';
      nextStep.textContent = state.lang === 'cs' ? 'Pro aktivaci počítače potřebujete aktivní licenci.' : 'An active licence is needed to connect a computer.';
      primaryLink.href = 'https://tomaspisar.cz/products/long-jump-replay/#buy';
      primaryLink.textContent = state.lang === 'cs' ? 'Získat licenci ↗' : 'Get a licence ↗';
    } else if (freeSlots > 0) {
      overviewTitle.textContent = state.lang === 'cs' ? 'Další počítač můžete připojit.' : 'Ready to connect another computer.';
      nextStep.textContent = state.lang === 'cs' ? `${freeSlots} ${freeSlots === 1 ? 'volné místo' : 'volná místa'} pro další počítač.` : `${freeSlots} ${freeSlots === 1 ? 'slot is' : 'slots are'} available for another computer.`;
      primaryLink.href = '/dashboard/activation';
      primaryLink.textContent = state.lang === 'cs' ? 'Připojit počítač' : 'Connect a computer';
    } else {
      overviewTitle.textContent = state.lang === 'cs' ? 'Všechna místa pro počítače jsou obsazená.' : 'All computer slots are in use.';
      nextStep.textContent = state.lang === 'cs' ? 'Všechna místa jsou obsazená. Uvolněte místo v seznamu počítačů.' : 'All slots are in use. Free one from your computers list.';
      primaryLink.href = '/dashboard/devices';
      primaryLink.textContent = state.lang === 'cs' ? 'Spravovat počítače' : 'Manage computers';
    }
    $('#overview-updated').textContent = new Intl.DateTimeFormat(state.lang === 'cs' ? 'cs-CZ' : 'en-GB', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date());
    $('#session-expiry').textContent = formatDate(data.session_expires_at);
    renderPasswordSecurity(Boolean(data.password_configured));

    $('#no-licence-state').hidden = hasActiveLicence;
    $('#no-licence-eyebrow').textContent = t(hasAnyLicence ? 'inactiveLicenceEyebrow' : 'noLicenceEyebrow');
    $('#no-licence-title').textContent = t(hasAnyLicence ? 'inactiveLicenceTitle' : 'noLicenceTitle');
    $('#no-licence-copy').textContent = t(hasAnyLicence ? 'inactiveLicenceCopy' : 'noLicenceCopy');
    $('#licence-cards').hidden = !hasAnyLicence;
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

  const loadDashboard = async (options = {}) => {
    const refresh = Boolean(options.refresh);
    if (!refresh) { $('#dashboard-loading').hidden = false; $('#dashboard-content').hidden = true; }
    setDashboardRetry(false);
    try { renderDashboard(await api('/api/portal/account')); setStatus('', '#account-status'); }
    catch (error) {
      if (error.status === 401) window.location.replace('/login');
      else { $('#dashboard-loading').hidden = true; if (!refresh) $('#dashboard-content').hidden = true; setStatus(error, '#account-status', 'error'); setDashboardRetry(true); }
    }
  };

  const initRegistration = () => {
    const form = $('#register-form');
    if (!form) return;
    const migration = new URLSearchParams(window.location.search).get('mode') === 'migration';
    const registrationState = { step: 'email', codeSent: false, setupToken: '', passwordRequired: true };
    const setText = (selector, en, cs) => { const element = $(selector); if (element) element.textContent = state.lang === 'cs' ? cs : en; };
    const busy = (value) => { const button = $('#register-submit'); if (button) { button.disabled = value; button.setAttribute('aria-busy', String(value)); } };
    const step = (value) => {
      registrationState.step = value;
      $('#register-email-step').hidden = value !== 'email';
      $('#register-code-step').hidden = value !== 'code';
      $('#register-details-step').hidden = value !== 'details';
      $('#register-change-email').hidden = value === 'email' || value === 'details';
      $('#register-resend-code').hidden = value !== 'code';
      setText('#register-submit', value === 'email' ? 'Continue' : value === 'code' ? 'Verify email' : 'Create account', value === 'email' ? 'Continue' : value === 'code' ? 'OvÄ›Å™it e-mail' : 'VytvoÅ™it ÃºÄet');
      if (value === 'email') $('#register-email').focus();
      if (value === 'code') $('#register-code').focus();
      if (value === 'details') (playerProduct ? $('#register-password') : $('#register-first-name')).focus();
    };
    const request = async () => {
      const email = $('#register-email').value.trim();
      if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) { $('#register-email').setAttribute('aria-invalid', 'true'); setStatus(t('invalidEmail'), '#register-status', 'error'); return; }
      state.email = email; setStatus(t('sending'), '#register-status'); busy(true);
      try { await api('/api/portal/register/request-code', { method: 'POST', body: JSON.stringify({ email }) }); registrationState.codeSent = true; step('code'); setStatus(t('sent'), '#register-status'); }
      catch (error) { setStatus(error, '#register-status', 'error'); } finally { busy(false); }
    };
    const verify = async () => {
      const code = $('#register-code').value.trim();
      if (!/^\d{6}$/.test(code)) { $('#register-code').setAttribute('aria-invalid', 'true'); setStatus(t('invalidCode'), '#register-status', 'error'); return; }
      setStatus(t('checking'), '#register-status'); busy(true);
      try { const result = await api('/api/portal/register/verify-code', { method: 'POST', body: JSON.stringify({ email: state.email, code }) }); registrationState.setupToken = result.setup_token; registrationState.passwordRequired = result.password_required !== false; $('#register-password-fields').hidden = !registrationState.passwordRequired; $('#register-password').required = registrationState.passwordRequired; $('#register-password-confirmation').required = registrationState.passwordRequired; step('details'); setStatus('', '#register-status'); }
      catch (error) { setStatus(error.status === 410 ? t('expiredCode') : error, '#register-status', 'error'); } finally { busy(false); }
    };
    const complete = async () => {
      const firstName = $('#register-first-name').value.trim(); const lastName = $('#register-last-name').value.trim();
      const password = $('#register-password').value; const confirmation = $('#register-password-confirmation').value;
      if (!playerProduct && (!firstName || !lastName)) { setStatus(t('profileRequired'), '#register-status', 'error'); return; }
      if (registrationState.passwordRequired && password !== confirmation) { setStatus(t('passwordMismatch'), '#register-status', 'error'); return; }
      if (registrationState.passwordRequired && !strongPassword(password)) { setStatus(t('passwordLength'), '#register-status', 'error'); return; }
      setStatus(t('checking'), '#register-status'); busy(true);
      try { await api('/api/portal/register/complete', { method: 'POST', body: JSON.stringify({ email: state.email, setup_token: registrationState.setupToken, first_name: firstName, last_name: lastName, club_name: $('#register-club-name').value.trim(), password, password_confirmation: confirmation }) }); setStatus(state.lang === 'cs' ? 'Účet vytvořen. Přesměrovávám na přihlášení…' : 'Account created. Returning to sign in…', '#register-status'); window.setTimeout(() => window.location.replace(playerProduct ? '/login?registered=1&product=economysuite&next=' + encodeURIComponent(playerNext) : '/login?registered=1'), 600); }
      catch (error) { setStatus(error, '#register-status', 'error'); } finally { busy(false); }
    };
    const loadMigration = async () => {
      try {
        const data = await api('/api/portal/account');
        if (!data.password_setup_required) { window.location.replace('/dashboard/overview'); return; }
        state.email = data.customer?.email || '';
        registrationState.passwordRequired = !data.password_configured;
        $('#register-email').value = state.email;
        $('#register-email-step').hidden = true; $('#register-code-step').hidden = true;
        $('#register-password-fields').hidden = !registrationState.passwordRequired;
        $('#register-password').required = registrationState.passwordRequired; $('#register-password-confirmation').required = registrationState.passwordRequired;
        step('details'); setStatus(state.lang === 'cs' ? 'Dokončete údaje svého účtu.' : 'Finish your account details.', '#register-status');
      } catch { step('email'); }
    };
    $('#register-change-email').addEventListener('click', () => { registrationState.codeSent = false; step('email'); setStatus('', '#register-status'); });
    $('#register-resend-code').addEventListener('click', request);
    form.addEventListener('submit', (event) => { event.preventDefault(); if (registrationState.step === 'email') return request(); if (registrationState.step === 'code') return verify(); return complete(); });
    if (migration) loadMigration(); else step('email');
  };

  const deactivate = async (deviceId) => {
    const accepted = await feedback?.confirm?.({
      title: state.lang === 'cs' ? 'Deaktivovat počítač?' : 'Deactivate this computer?',
      description: state.lang === 'cs' ? 'Počítač se odpojí od licence a uvolní místo pro jinou stanici.' : 'This computer will be disconnected from the licence and its slot will be available for another station.',
      confirmLabel: state.lang === 'cs' ? 'Deaktivovat' : 'Deactivate',
      cancelLabel: state.lang === 'cs' ? 'Zrušit' : 'Cancel',
      destructive: true
    });
    if (accepted === false) return;
    setStatus(t('deactivating'));
    try {
      await api('/api/portal/deactivate-device', { method: 'POST', body: JSON.stringify({ device_id: deviceId }) });
      await loadDashboard();
      notify('success', t('deviceDeactivated'), state.lang === 'cs' ? 'Počítač deaktivován' : 'Computer deactivated');
    } catch (error) { setStatus(error, '#account-status', 'error'); }
  };

  const deleteDevice = async (deviceId) => {
    const accepted = await feedback?.confirm?.({
      title: state.lang === 'cs' ? 'Odstranit počítač?' : 'Remove this computer?',
      description: state.lang === 'cs' ? 'Trvale se odstraní deaktivovaný počítač i jeho historie aktivity. Tuto akci nelze vrátit.' : 'The deactivated computer and its activity history will be permanently removed. This cannot be undone.',
      confirmLabel: state.lang === 'cs' ? 'Odstranit' : 'Remove',
      cancelLabel: state.lang === 'cs' ? 'Zrušit' : 'Cancel',
      destructive: true
    });
    if (accepted === false) return;
    try {
      await api('/api/portal/delete-device', { method: 'POST', body: JSON.stringify({ device_id: deviceId }) });
      await loadDashboard();
      notify('success', t('deviceDeleted'), state.lang === 'cs' ? 'Počítač odstraněn' : 'Computer removed');
    } catch (error) { setStatus(error, '#account-status', 'error'); }
  };

  const showDeviceDetails = async (deviceId) => {
    try {
      const data = await api(`/api/portal/device-details?device_id=${encodeURIComponent(deviceId)}`);
      const device = data.device;
      $('#device-details-title').textContent = device.device_name || 'LongJumpReplay computer';
      $('#device-details-content').innerHTML = `<dl class="device-facts"><div><dt>${t('status')}</dt><dd>${escapeHtml(device.status)}</dd></div><div><dt>${t('method')}</dt><dd>${device.activation_method === 'key' ? t('keyMethod') : t('emailMethod')}</dd></div><div><dt>${t('activated')}</dt><dd>${formatDateTime(device.activated_at)}</dd></div><div><dt>${t('lastActive')}</dt><dd>${formatDateTime(device.last_verified_at)}</dd></div></dl><details class="advanced-details"><summary>${state.lang === 'cs' ? 'Zobrazit technické údaje a aktivitu' : 'Show technical details and activity'}</summary><dl class="device-facts"><div><dt>App version</dt><dd>${escapeHtml(device.app_version || '—')}</dd></div><div><dt>Windows</dt><dd>${escapeHtml(device.os_version || '—')}</dd></div><div><dt>Architecture</dt><dd>${escapeHtml(device.architecture || '—')}</dd></div><div><dt>Device ID</dt><dd><code>${escapeHtml(device.id)}</code></dd></div><div><dt>Machine ID</dt><dd><code>${escapeHtml(device.machine_id)}</code></dd></div><div><dt>Key generation</dt><dd>${escapeHtml(device.activation_key_generation || '—')}</dd></div></dl><div class="activity-list">${(data.activity || []).map((item) => `<article><strong>${escapeHtml(item.event_type)}</strong><span>${formatDateTime(item.created_at)}</span><code>${escapeHtml(item.ip_address || '—')}</code><span>${escapeHtml(item.country || '—')}</span></article>`).join('') || `<p class="muted">${state.lang === 'cs' ? 'Žádná historie aktivity.' : 'No activity history.'}</p>`}</div></details>`;
      $('#device-details-dialog').showModal();
    } catch (error) { setStatus(error, '#account-status', 'error'); }
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
    } catch (error) { setStatus(error, '#account-status', 'error'); }
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
      setStatus('', '#account-status');
      notify('success', state.lang === 'cs' ? 'Zkopírováno' : 'Copied', state.lang === 'cs' ? 'Zkopírováno do schránky' : 'Copied to clipboard');
    } catch {
      notify('error', state.lang === 'cs' ? 'Klíč se nepodařilo zkopírovat. Zkuste to znovu.' : 'The key could not be copied. Try again.', state.lang === 'cs' ? 'Kopírování selhalo' : 'Copy failed');
    } finally {
      button.disabled = false;
      button.removeAttribute('aria-busy');
      button.textContent = state.lang === 'cs' ? 'Kopírovat klíč' : 'Copy key';
    }
  };

  const regenerateActivationKey = async () => {
    const keyed = (state.account?.devices || []).filter((device) => device.license_id === state.keyLicenceId && device.status === 'active' && device.activation_method === 'key').length;
    const accepted = await feedback?.confirm?.({
      title: state.lang === 'cs' ? 'Vygenerovat nový klíč?' : 'Generate a new key?',
      description: state.lang === 'cs' ? `Odpojí se ${keyed} počítačů aktivovaných tímto klíčem. Počítače aktivované e-mailem zůstanou připojené.` : `This disconnects ${keyed} key-activated computer(s). Email-activated computers stay connected.`,
      confirmLabel: state.lang === 'cs' ? 'Vygenerovat klíč' : 'Generate key',
      cancelLabel: state.lang === 'cs' ? 'Zrušit' : 'Cancel',
      destructive: true
    });
    if (accepted === false) return;
    try {
      const data = await api('/api/portal/activation-key/regenerate', { method: 'POST', body: JSON.stringify({ license_id: state.keyLicenceId }) });
      state.keyVisible = true; state.keyValue = data.key;
      $('#activation-key-value').textContent = data.key;
      $('#activation-key-reveal').textContent = state.lang === 'cs' ? 'Skrýt klíč' : 'Hide key';
      notify('success', state.lang === 'cs' ? `Nový klíč je připraven. Odpojeno počítačů: ${data.disconnected_devices}.` : `New key ready. Disconnected computers: ${data.disconnected_devices}.`, state.lang === 'cs' ? 'Klíč obnoven' : 'Key regenerated');
      if (state.account) state.account.devices = state.account.devices.map((device) => device.license_id === state.keyLicenceId && device.activation_method === 'key' ? { ...device, status: 'deactivated' } : device);
      renderDevices(state.account.devices, new Set((state.account.licenses || []).filter((licence) => licence.status === 'active').map((licence) => licence.id)));
    } catch (error) { setStatus(error, '#account-status', 'error'); }
  };

  const signOut = async () => {
    try { await api('/api/portal/logout', { method: 'POST', body: '{}' }); }
    finally { window.location.replace('/login'); }
  };

  const openBilling = async () => {
    setStatus(t('sending'));
    try { const data = await api('/api/portal/billing', { method: 'POST', body: '{}' }); window.location.href = data.url; }
    catch (error) { setStatus(error, '#account-status', 'error'); }
  };

  const initDashboard = () => {
    const pendingPairing = capturePairingFromLocation();
    renderDashboardRoute(false);
    document.addEventListener('click', (event) => {
      const button = event.target.closest('[data-deactivate]');
      if (button) deactivate(button.dataset.deactivate);
      const deleteButton = event.target.closest('[data-delete-device]');
      if (deleteButton) deleteDevice(deleteButton.dataset.deleteDevice);
      const detailsButton = event.target.closest('[data-details]');
      if (detailsButton) showDeviceDetails(detailsButton.dataset.details);
    });
    document.querySelectorAll('[data-open-billing]').forEach((button) => button.addEventListener('click', openBilling));
    $('#logout-button')?.addEventListener('click', signOut);
    $('#security-logout-button')?.addEventListener('click', signOut);
    $('#dashboard-refresh')?.addEventListener('click', async (event) => {
      const button = event.currentTarget;
      feedback?.busy(button, true);
      try {
        await loadDashboard({ refresh: true });
        if (!button.hidden) return;
        notify('success', state.lang === 'cs' ? 'Účet byl obnoven.' : 'Account refreshed.', state.lang === 'cs' ? 'Obnoveno' : 'Refreshed');
      } finally { feedback?.busy(button, false); }
    });
    $('#profile-form')?.addEventListener('submit', async (event) => {
      event.preventDefault();
      const firstName = $('#profile-first-name')?.value.trim() || '';
      const lastName = $('#profile-last-name')?.value.trim() || '';
      const clubName = $('#profile-club-name')?.value.trim() || '';
      if (!firstName || !lastName) { setStatus(t('profileRequired'), '#profile-status', 'error'); return; }
      const button = event.currentTarget.querySelector('button[type="submit"]');
      button.disabled = true;
      setStatus(state.lang === 'cs' ? 'Ukládám profil…' : 'Saving profile…', '#profile-status');
      try {
        await api('/api/portal/profile', { method: 'POST', body: JSON.stringify({ first_name: firstName, last_name: lastName, club_name: clubName }) });
        setStatus('', '#profile-status');
        notify('success', t('profileSaved'), state.lang === 'cs' ? 'Profil uložen' : 'Profile saved');
        await loadDashboard();
      } catch (error) { setStatus(error, '#profile-status', 'error'); }
      finally { button.disabled = false; }
    });
    $('#password-enroll-form')?.addEventListener('submit', async (event) => {
      event.preventDefault();
      const form = event.currentTarget;
      const newPassword = $('#enroll-password')?.value || '';
      const confirmation = $('#confirm-enroll-password')?.value || '';
      if (newPassword !== confirmation) { setStatus(t('passwordMismatch'), '#profile-status', 'error'); return; }
      if (!strongPassword(newPassword)) { setStatus(t('passwordLength'), '#profile-status', 'error'); return; }
      const configured = form.dataset.configured === 'true';
      const body = configured
        ? { current_password: $('#current-password')?.value || '', new_password: newPassword }
        : { password: newPassword };
      if (configured && body.current_password.length < 12) { setStatus(state.lang === 'cs' ? 'Zadejte současné heslo.' : 'Enter your current password.', '#profile-status', 'error'); return; }
      setStatus(state.lang === 'cs' ? 'Ukládám heslo…' : 'Saving password…', '#profile-status');
      try { await api(configured ? '/api/portal/password/change' : '/api/portal/password/enroll', { method: 'POST', body: JSON.stringify(body) }); setStatus('', '#profile-status'); notify('success', t('passwordSaved'), state.lang === 'cs' ? 'Heslo uloženo' : 'Password saved'); await loadDashboard(); }
      catch (error) { setStatus(error, '#profile-status', 'error'); }
    });
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
        catch (error) { setStatus(error, '#account-status', 'error'); }
      }
    });
    loadDashboard().then(() => {
      if (dashboardRoute === 'activation') {
        if (pendingPairing) inspectPairing(pendingPairing);
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
  if (page === 'register') initRegistration();
  if (page === 'dashboard') initDashboard();
})();
