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
      route: "/products/long-jump-replay/",
      downloadRoute: "/products/long-jump-replay/download/",
      licensingRoute: "/products/long-jump-replay/licensing/",
      privacyRoute: "/products/long-jump-replay/privacy/",
      version: "6.2.10",
      versionShort: "6.2",
      price: "4 990 Kč",
      platform: "Windows",
      installerUrl: "https://files.tomaspisar.cz/LJR_setup.exe",
      releaseManifestUrl: "https://files.tomaspisar.cz/latest.json",
      trialHours: 72,
      trialExportLimit: 3,
      screenshots: ["/assets/images/long-jump-replay/main-screen.png", "/assets/images/long-jump-replay/recordings.png", "/assets/images/long-jump-replay/competition-board.png"]
    },
    relayLab: {
      key: "relaylab",
      name: "RelayLab",
      route: "/products/relaylab/",
      platform: "Web",
      status: "Available"
    }
  }
};
