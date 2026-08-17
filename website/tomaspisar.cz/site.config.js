window.SITE_CONFIG = {
  siteUrl: "https://tomaspisar.cz",
  developer: { name: "Tomáš Pisár", email: "info@tomaspisar.cz", github: "https://github.com/Trueborder" },
  // Licensing values shown on the website. Keep these in step with the values
  // the licensing backend actually enforces; every page reads them from here
  // through [data-license-devices], [data-license-grace] and
  // [data-license-updates], so changing a number here changes it site-wide.
  licensing: { deviceLimit: 2, offlineGraceDays: 30, updateMonths: 12 },
  products: { longJumpReplay: { key: "longjumpreplay", name: "LongJumpReplay", version: "3.1.0", versionShort: "3.1", price: "4 990 Kč", platform: "Windows", installerUrl: "https://files.tomaspisar.cz/LJR_setup.exe", trialHours: 72, trialExportLimit: 3, screenshots: ["/screenshots/main-screen.png", "/screenshots/recordings.png", "/screenshots/competition-board.png"] } }
};
