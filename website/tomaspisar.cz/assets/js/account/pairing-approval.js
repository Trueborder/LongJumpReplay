(function () {
  'use strict';

  const API = 'https://api.tomaspisar.cz';
  const PENDING_PAIRING_KEY = 'ljr_pending_pairing_v1';
  const $ = (selector) => document.querySelector(selector);
  const loading = $('#pairing-loading');
  const errorBox = $('#pairing-error');
  const requestBox = $('#pairing-request');
  const resultBox = $('#pairing-result');
  const approveButton = $('#pairing-approve');
  const declineButton = $('#pairing-decline');
  const licenceSelect = $('#pairing-licence');
  const licenceNote = $('#pairing-licence-note');
  let token = '';
  let pollTimer = 0;
  let terminal = false;

  const copy = {
    en: {
      signIn: 'Sign in to approve this computer.',
      invalid: 'This pairing link is invalid or has expired.',
      noLicence: 'No active licence has an available computer slot.',
      chooseLicence: 'Choose an active licence with an available computer slot.',
      waiting: 'Approved. Waiting for the computer to finish activation…',
      activating: 'Activation is being completed on the computer…',
      activated: 'Computer approved and activated.',
      declined: 'This computer pairing was declined.',
      expired: 'This pairing request has expired.',
      failed: 'Activation could not be completed.',
      closeHint: 'You can close this tab.'
    },
    cs: {
      signIn: 'Pro schválení tohoto počítače se přihlaste.',
      invalid: 'Tento párovací odkaz je neplatný nebo jeho platnost skončila.',
      noLicence: 'Žádná aktivní licence nemá volné místo pro počítač.',
      chooseLicence: 'Vyberte aktivní licenci s volným místem pro počítač.',
      waiting: 'Schváleno. Čekání na dokončení aktivace v počítači…',
      activating: 'Aktivace se dokončuje v počítači…',
      activated: 'Počítač byl schválen a aktivován.',
      declined: 'Párování tohoto počítače bylo odmítnuto.',
      expired: 'Platnost této žádosti skončila.',
      failed: 'Aktivaci se nepodařilo dokončit.',
      closeHint: 'Tuto kartu můžete zavřít.'
    }
  };

  const language = () => {
    try { return sessionStorage.getItem('site-language') === 'cs' ? 'cs' : 'en'; } catch (_) { return 'en'; }
  };
  const text = (key) => copy[language()][key] || copy.en[key];
  const rememberToken = (value) => {
    try { sessionStorage.setItem(PENDING_PAIRING_KEY, JSON.stringify({ token: value, savedAt: Date.now() })); } catch (_) { /* best effort */ }
  };
  const rememberedToken = () => {
    try {
      const stored = JSON.parse(sessionStorage.getItem(PENDING_PAIRING_KEY) || 'null');
      if (!stored || Date.now() - Number(stored.savedAt || 0) > 15 * 60 * 1000) return '';
      return /^[A-Za-z0-9_-]{20,256}$/.test(String(stored.token || '')) ? String(stored.token) : '';
    } catch (_) { return ''; }
  };
  const extractToken = () => {
    const params = new URLSearchParams(window.location.hash.replace(/^#/, '') || window.location.search.replace(/^\?/, ''));
    const value = params.get('pair') || '';
    if (!/^[A-Za-z0-9_-]{20,256}$/.test(value)) return rememberedToken();
    rememberToken(value);
    if (window.location.hash || window.location.search) history.replaceState(null, '', window.location.pathname);
    return value;
  };
  const escapeValue = (value) => String(value ?? '').trim() || '—';
  const formatDate = (value) => {
    const date = new Date(Number(value) * 1000);
    return Number.isNaN(date.getTime()) ? '—' : new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(date);
  };
  const setBusy = (busy) => {
    approveButton.disabled = busy;
    declineButton.disabled = busy;
    licenceSelect.disabled = busy;
    approveButton.setAttribute('aria-busy', busy ? 'true' : 'false');
  };
  const showError = (message) => {
    loading.hidden = true;
    requestBox.hidden = true;
    errorBox.hidden = false;
    errorBox.textContent = message;
  };
  const api = async (path, body) => {
    const response = await fetch(API + path, {
      method: 'POST', credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      const exception = new Error(payload.message || text('failed'));
      exception.status = response.status;
      exception.code = payload.error;
      throw exception;
    }
    return payload;
  };
  const setField = (name, value) => { const field = document.querySelector(`[data-pairing-field="${name}"]`); if (field) field.textContent = escapeValue(value); };
  const showResult = (title, message, kind) => {
    terminal = true;
    if (pollTimer) window.clearTimeout(pollTimer);
    requestBox.hidden = true;
    loading.hidden = true;
    errorBox.hidden = true;
    resultBox.hidden = false;
    $('#pairing-result-icon').textContent = kind === 'success' ? '✓' : kind === 'declined' ? '×' : '!';
    $('#pairing-result-icon').dataset.state = kind;
    $('#pairing-result-title').textContent = title;
    $('#pairing-result-message').textContent = message;
    approveButton.disabled = true;
    declineButton.disabled = true;
  };
  const handleResult = (payload) => {
    if (payload.status === 'activated') return showResult(text('activated'), text('activated'), 'success');
    if (payload.status === 'declined') return showResult(text('declined'), payload.message || text('declined'), 'declined');
    if (payload.status === 'expired') return showResult(text('expired'), payload.message || text('expired'), 'warning');
    if (payload.status === 'failed') return showResult(text('failed'), payload.message || text('failed'), 'error');
    $('#pairing-result-message').textContent = payload.status === 'activating' ? text('activating') : text('waiting');
    if (!terminal) pollTimer = window.setTimeout(pollResult, 1500);
  };
  const pollResult = async () => {
    if (terminal) return;
    try { handleResult(await api('/api/portal/pairing/result', { pairing_token: token })); }
    catch (exception) {
      if (exception.status === 401) return showError(text('signIn'));
      if (exception.status === 410 || exception.code === 'pairing_expired') return showResult(text('expired'), text('expired'), 'warning');
      if (!terminal) pollTimer = window.setTimeout(pollResult, 2500);
    }
  };
  const renderRequest = (payload) => {
    const pairing = payload.pairing || {};
    setField('device_name', pairing.device_name);
    setField('app_version', pairing.app_version);
    setField('os_version', pairing.os_version);
    setField('architecture', pairing.architecture);
    setField('created_at', formatDate(pairing.created_at));
    setField('expires_at', formatDate(pairing.expires_at));
    licenceSelect.innerHTML = '';
    const eligible = (payload.licenses || []).filter((licence) => licence.can_approve);
    (payload.licenses || []).forEach((licence) => {
      const option = document.createElement('option');
      option.value = licence.id;
      option.disabled = !licence.can_approve;
      option.textContent = `${licence.type === 'lifetime' ? 'Lifetime' : 'Subscription'} · ${licence.active_devices}/${licence.max_devices} computers${licence.can_approve ? '' : ' · unavailable'}`;
      licenceSelect.appendChild(option);
    });
    approveButton.disabled = eligible.length === 0 || pairing.status !== 'pending';
    declineButton.disabled = pairing.status !== 'pending';
    licenceSelect.disabled = eligible.length === 0 || pairing.status !== 'pending';
    licenceNote.textContent = eligible.length ? text('chooseLicence') : text('noLicence');
    loading.hidden = true;
    requestBox.hidden = false;
    if (pairing.status === 'used') return showResult(text('activated'), text('activated'), 'success');
    if (pairing.status === 'declined') return showResult(text('declined'), text('declined'), 'declined');
    if (pairing.status === 'expired') return showResult(text('expired'), text('expired'), 'warning');
    if (pairing.status === 'failed') return showResult(text('failed'), text('failed'), 'error');
    if (pairing.status === 'approved' || pairing.status === 'activating') {
      requestBox.hidden = true;
      resultBox.hidden = false;
      $('#pairing-result-message').textContent = pairing.status === 'activating' ? text('activating') : text('waiting');
      pollResult();
    }
  };
  const load = async () => {
    if (!token) return showError(text('invalid'));
    try { renderRequest(await api('/api/portal/pairing/view', { pairing_token: token })); }
    catch (exception) {
      if (exception.status === 401) {
        rememberToken(token);
        window.location.replace('/login');
        return;
      }
      showError(exception.status === 410 ? text('expired') : exception.message || text('invalid'));
    }
  };
  approveButton.addEventListener('click', async () => {
    if (!licenceSelect.value) return;
    setBusy(true);
    try {
      await api('/api/portal/pairing/approve', { pairing_token: token, license_id: licenceSelect.value });
      $('#pairing-result-message').textContent = text('waiting');
      requestBox.hidden = true;
      resultBox.hidden = false;
      await pollResult();
    } catch (exception) {
      setBusy(false);
      if (exception.status === 410) showResult(text('expired'), text('expired'), 'warning');
      else { licenceNote.textContent = exception.message || text('failed'); licenceNote.dataset.state = 'warning'; }
    }
  });
  declineButton.addEventListener('click', async () => {
    setBusy(true);
    try { await api('/api/portal/pairing/decline', { pairing_token: token }); showResult(text('declined'), text('declined'), 'declined'); }
    catch (exception) { setBusy(false); licenceNote.textContent = exception.message || text('failed'); licenceNote.dataset.state = 'warning'; }
  });
  $('#pairing-close').addEventListener('click', () => {
    window.close();
    window.setTimeout(() => { if (!document.hidden) { $('#pairing-result-message').textContent = text('closeHint'); } }, 100);
  });
  token = extractToken();
  load();
}());
