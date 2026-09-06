window.SITE_CONFIG = {
  siteUrl: "https://tomaspisar.cz",
  contact: { apiUrl: "https://api.tomaspisar.cz/api/contact", turnstileSiteKey: "0x4AAAAAAEj9IbwE21Qhi_lO" },
  developer: { name: "Tomáš Pisár", email: "info@tomaspisar.cz", github: "https://github.com/Trueborder" },
  // Licensing values shown on the website. Keep these in step with the values
  // the licensing backend actually enforces; every page reads them from here
  // through [data-license-devices], [data-license-grace] and
  // [data-license-updates], so changing a number here changes it site-wide.
  licensing: { deviceLimit: 2, offlineGraceDays: 30, updateMonths: 12 },
  // Two ways to buy the same software. Both activate identically and both get
  // the same device limit; they differ only in how they are paid for.
  plans: { lifetime: { label: "Lifetime", labelCs: "Doživotní" }, monthly: { label: "Monthly", labelCs: "Měsíční", price: "379 Kč", period: "month", periodCs: "měsíc" } },
  products: { longJumpReplay: { key: "longjumpreplay", name: "LongJumpReplay", version: "4.0.0", versionShort: "4.0", price: "4 990 Kč", platform: "Windows", installerUrl: "https://files.tomaspisar.cz/LJR_setup.exe", releaseManifestUrl: "https://files.tomaspisar.cz/latest.json", trialHours: 72, trialExportLimit: 3, screenshots: ["/screenshots/main-screen.png", "/screenshots/recordings.png", "/screenshots/competition-board.png"] } }
};
