// Kept as a small compatibility layer for deployments that swap the public
// download label after the main page script has loaded.
(() => {
  const applyInstallerCopy = () => {
    const isCzech = document.documentElement.lang === "cs";
    const values = isCzech
      ? {
          downloadCta: "Stáhnout instalátor",
          offerLead: "Trvalá licence pro jeden počítač s Windows včetně instalátoru pro Windows a e-mailové podpory.",
          offerItemTwo: "Instalátor pro Windows",
          downloadButton: "Stáhnout instalátor <span>↓</span>",
          downloadLead: "Instalátor umístí LongJumpReplay do Program Files a přidá běžnou položku do nabídky Start. Záznamy a nastavení zůstanou ve vašem uživatelském profilu."
        }
      : {
          downloadCta: "Download installer",
          offerLead: "A perpetual license for one Windows computer, with the Windows installer and email support included.",
          offerItemTwo: "Windows installer",
          downloadButton: "Download installer <span>↓</span>",
          downloadLead: "The Windows installer places LongJumpReplay in Program Files and adds a normal Start Menu entry. Recordings and settings stay in your user profile."
        };

    Object.entries(values).forEach(([key, value]) => {
      document.querySelectorAll(`[data-copy="${key}"]`).forEach((node) => { node.innerHTML = value; });
    });
  };

  applyInstallerCopy();
  document.getElementById("languageToggle")?.addEventListener("click", () => setTimeout(applyInstallerCopy, 0));
})();
