(() => {
  const strings = {
    en: {
      downloadCta: 'Download installer',
      offerLead: 'A perpetual license for one Windows computer, with the Windows installer and email support included.',
      offerItemTwo: 'Windows installer',
      downloadButton: 'Download installer <span>↓</span>',
      downloadLead: 'The installer places LongJumpReplay into Program Files and adds a normal Windows Start Menu entry. Your recordings and settings stay in your user profile.'
    },
    cs: {
      downloadCta: 'Stáhnout instalátor',
      offerLead: 'Trvalá licence pro jeden počítač s Windows, včetně instalátoru pro Windows a e-mailové podpory.',
      offerItemTwo: 'Instalátor pro Windows',
      downloadButton: 'Stáhnout instalátor <span>↓</span>',
      downloadLead: 'Instalátor umístí LongJumpReplay do Program Files a přidá běžnou položku do nabídky Start. Záznamy a nastavení zůstanou ve vašem uživatelském profilu.'
    }
  };
  const apply = () => {
    const values = strings[document.documentElement.lang] || strings.en;
    Object.entries(values).forEach(([key, value]) => {
      document.querySelectorAll(`[data-copy="${key}"]`).forEach((node) => { node.innerHTML = value; });
    });
  };
  apply();
  document.getElementById('languageToggle')?.addEventListener('click', () => setTimeout(apply, 0));
})();
