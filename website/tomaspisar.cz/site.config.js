window.SITE_CONFIG = {
  siteUrl: "https://tomaspisar.cz",
  contact: { apiUrl: "https://api.tomaspisar.cz/api/contact", turnstileSiteKey: "0x4AAAAAAEj9IbwE21Qhi_lO" },
  developer: { name: "Tomáš Pisár", email: "info@tomaspisar.cz", github: "https://github.com/Trueborder" },
  licensing: { deviceLimit: 2, offlineGraceDays: 30, updateMonths: 12 },
  plans: { lifetime: { label: "Lifetime", labelCs: "Doživotní" }, monthly: { label: "Monthly", labelCs: "Měsíční", price: "379 Kč", period: "month", periodCs: "měsíc" } },
  products: {
    longJumpReplay: {
      key: "longjumpreplay",
      name: "LongJumpReplay",
      route: "/software/longjumpreplay/",
      downloadRoute: "/software/longjumpreplay/download/",
      licensingRoute: "/software/longjumpreplay/licensing/",
      privacyRoute: "/software/longjumpreplay/privacy/",
      version: "6.2.10",
      versionShort: "6.2",
      price: "4 990 Kč",
      platform: "Windows",
      installerUrl: "https://files.tomaspisar.cz/LJR_setup.exe",
      releaseManifestUrl: "https://files.tomaspisar.cz/latest.json",
      trialHours: 72,
      trialExportLimit: 3,
      screenshots: ["/screenshots/main-screen.png", "/screenshots/recordings.png", "/screenshots/competition-board.png"]
    },
    relayLab: {
      key: "relaylab",
      name: "RelayLab",
      route: "/software/relaylab/",
      platform: "Web",
      status: "Available"
    }
  }
};
