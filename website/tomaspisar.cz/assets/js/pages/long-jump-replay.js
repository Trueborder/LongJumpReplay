(() => {
  const root = document.querySelector('#ljr-public-catalog'); if (!root) return;
  const escapeHtml = (v) => String(v ?? '').replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
  const money = (minor, currency) => typeof minor === 'number' ? new Intl.NumberFormat(document.documentElement.lang === 'cs' ? 'cs-CZ' : 'en-GB',{style:'currency',currency:(currency||'czk').toUpperCase()}).format(minor/100) : '—';
  fetch('https://api.tomaspisar.cz/api/longjumpreplay/catalog').then(response => response.ok ? response.json() : Promise.reject()).then(data => {
    const items = data.items || [];
    root.innerHTML = items.map(item => `<article class="buy-option"><p class="eyebrow">${item.license_type === 'subscription' ? 'MONTHLY' : 'LIFETIME'}</p><h3>${item.license_type === 'subscription' ? 'Měsíční licence' : 'Doživotní licence'}</h3><strong class="buy-option-price">${money(item.amount_minor,item.currency)}</strong><p>${item.device_limit} počítače, aktivace e-mailem, offline ověření až ${item.offline_verification_days} dní.</p><a class="button button-primary" href="https://account.tomaspisar.cz/checkout?product=longjumpreplay&price=${encodeURIComponent(item.price_id)}">Koupit licenci →</a></article>`).join('') || '<p>Ceník je dočasně nedostupný. Napište podpoře pro aktuální nabídku.</p>';
  }).catch(() => { root.innerHTML = '<p class="notice">Aktuální ceny se nepodařilo načíst. Zkuste to později nebo kontaktujte podporu.</p>'; });
})();
