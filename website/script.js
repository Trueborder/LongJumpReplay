(() => {
  const config = window.LJR_SITE_CONFIG || {};
  const copy = {
    en: {
      skip: "Skip to content",
      navWorkflow: "Workflow",
      navFeatures: "Features",
      navOffer: "Offer",
      navDownload: "Download",
      downloadCta: "Download installer",
      eyebrow: "TAKE-OFF REVIEW / WINDOWS 3.1",
      heroTitle: "Keep the<br>runway live.<br><em>Review the call.</em>",
      heroLead: "LongJumpReplay freezes the moment you need, while capture keeps running for the next athlete.",
      heroButton: "Get the Windows installer <span>↗</span>",
      heroSecondary: "See the workflow <span>↓</span>",
      factOneLabel: "01", factOne: "Live capture",
      factTwoLabel: "02", factTwo: "Frame review",
      factThreeLabel: "03", factThree: "Operator decides",
      stripOne: "Built for the judge station",
      stripTwo: "Works with your camera",
      stripThree: "No cloud required",
      stripFour: "English / Czech",
      workflowEyebrow: "THE DECISION WINDOW",
      workflowTitle: "One motion.<br><em>Four useful states.</em>",
      workflowLead: "The decisive frame should not disappear into a rolling buffer. LongJumpReplay makes the review repeatable, clear, and quick to return from.",
      stepOneTitle: "Capture", stepOneText: "The camera keeps running.",
      stepTwoTitle: "Freeze", stepTwoText: "Pin the exact attempt.",
      stepThreeTitle: "Replay", stepThreeText: "Step frame by frame.",
      stepFourTitle: "Decide", stepFourText: "Mark valid, foul, or review.",
      featuresEyebrow: "FOR PEOPLE AT THE PIT",
      featuresTitle: "Quiet tools for<br><em>high-pressure calls.</em>",
      featuresLead: "Designed around a real competition: fast capture, precise review, and an evidence trail you can explain.",
      featureOneTitle: "See the line clearly",
      featureOneText: "Place the board guide and take-off region directly on the video so the decision stays anchored to the frame.",
      featureOneTag: "BOARD CALIBRATION",
      featureTwoTitle: "Review without rushing",
      featureTwoText: "Use the timeline, frame stepping, keyboard controls, or ShuttleXpress to find the moment with confidence.",
      featureTwoTag: "FRAME CONTROL",
      featureThreeTitle: "Keep attempts in order",
      featureThreeText: "The competition board keeps recordings, athletes, attempts, decisions, and exports together.",
      featureThreeTag: "COMPETITION BOARD",
      featureFourTitle: "Evidence, not automation",
      featureFourText: "LongJumpReplay helps an official review the moment. It does not measure distance or decide Valid/Foul for you.",
      featureFourTag: "OPERATOR CONTROL",
      officialsEyebrow: "FOR OFFICIALS",
      officialsTitle: "A second look<br><em>before the next jump.</em>",
      officialsText: "Keep the competition moving while giving close take-offs the attention they deserve.",
      officialsLink: "See the license offer <span>→</span>",
      clubsEyebrow: "FOR CLUBS &amp; COACHES",
      clubsTitle: "Make technical<br><em>review repeatable.</em>",
      clubsText: "Use the same controls for training review, event preparation, and athlete feedback.",
      clubsLink: "Download for Windows <span>→</span>",
      screensEyebrow: "THE STATION, AT A GLANCE",
      screensTitle: "A focused view<br><em>when it counts.</em>",
      screensLead: "Choose a high-contrast dark theme or a clean light theme for the room, screen, and operator in front of it.",
      offerEyebrow: "THE LAUNCH OFFER",
      offerTitle: "One station.<br><em>One clear license.</em>",
      offerLead: "A perpetual license for one Windows computer, with the Windows installer and email support included.",
      offerItemOne: "Perpetual single-computer license",
      offerItemTwo: "Windows installer",
      offerItemThree: "English and Czech interface",
      offerItemFour: "Email support from the developer",
      priceKicker: "LONGJUMPREPLAY 3.1",
      priceNote: "one Windows computer · perpetual",
      priceButton: "Ask about a license <span>↗</span>",
      priceFootnote: "No online account. No cloud upload. Contact us for a machine-bound activation key.",
      downloadEyebrow: "READY WHEN YOU ARE",
      downloadTitle: "Install the judge station.",
      downloadLead: "The Windows installer places LongJumpReplay in Program Files and adds a normal Start Menu entry. Recordings and settings stay in your user profile.",
      downloadButton: "Download installer <span>↓</span>",
      checksum: "SHA-256 checksum <span>↗</span>",
      contactEyebrow: "LET'S TALK ABOUT YOUR SETUP",
      contactTitle: "Bring a clearer<br><em>call to the pit.</em>",
      contactText: "Tell us about your camera, event format, or club workflow. We'll reply with the next step and the activation process for your computer.",
      footerNote: "Live capture · precise review · operator control"
    },
    cs: {
      skip: "Přejít na obsah",
      navWorkflow: "Postup", navFeatures: "Funkce", navOffer: "Nabídka", navDownload: "Stažení",
      downloadCta: "Stáhnout instalátor",
      eyebrow: "KONTROLA ODRAZU / WINDOWS 3.1",
      heroTitle: "Dráha zůstává<br>živá.<br><em>Rozhodněte s jistotou.</em>",
      heroLead: "LongJumpReplay zmrazí potřebný okamžik, zatímco záznam pokračuje pro dalšího závodníka.",
      heroButton: "Stáhnout instalátor pro Windows <span>↗</span>",
      heroSecondary: "Prohlédnout postup <span>↓</span>",
      factOneLabel: "01", factOne: "Živý záznam",
      factTwoLabel: "02", factTwo: "Kontrola snímků",
      factThreeLabel: "03", factThree: "Rozhoduje obsluha",
      stripOne: "Pro stanoviště rozhodčího", stripTwo: "Funguje s vaší kamerou", stripThree: "Bez cloudu", stripFour: "Anglicky / česky",
      workflowEyebrow: "OKAMŽIK ROZHODNUTÍ",
      workflowTitle: "Jeden pohyb.<br><em>Čtyři užitečné stavy.</em>",
      workflowLead: "Rozhodující snímek nemá zmizet v posouvajícím se bufferu. LongJumpReplay mění živý obraz v klidný a opakovatelný postup kontroly.",
      stepOneTitle: "Záznam", stepOneText: "Kamera stále běží.",
      stepTwoTitle: "Zmrazit", stepTwoText: "Uchovat přesný pokus.",
      stepThreeTitle: "Přehrát", stepThreeText: "Projít snímek po snímku.",
      stepFourTitle: "Rozhodnout", stepFourText: "Označit platný, přešlap nebo kontrolu.",
      featuresEyebrow: "PRO LIDI U PÍSKOVIŠTĚ",
      featuresTitle: "Klidné nástroje pro<br><em>náročná rozhodnutí.</em>",
      featuresLead: "Navrženo podle rytmu skutečné soutěže: rychlý záznam, přesná kontrola a důkaz, který můžete vysvětlit.",
      featureOneTitle: "Čáru vidíte jasně",
      featureOneText: "Umístěte vodítko prkna a oblast odrazu přímo do videa, aby rozhodnutí zůstalo ukotvené ve snímku.",
      featureOneTag: "KALIBRACE PRKNA",
      featureTwoTitle: "Kontrola bez spěchu",
      featureTwoText: "Časová osa, krokování snímků, klávesnice nebo ShuttleXpress vám pomohou najít okamžik s jistotou.",
      featureTwoTag: "OVLÁDÁNÍ SNÍMKŮ",
      featureThreeTitle: "Každý pokus na svém místě",
      featureThreeText: "Soutěžní tabule propojí záznamy, závodníky, pokusy, rozhodnutí a exporty.",
      featureThreeTag: "SOUTĚŽNÍ TABULE",
      featureFourTitle: "Důkaz, ne automat",
      featureFourText: "LongJumpReplay pomáhá rozhodčímu prohlédnout okamžik. Neměří délku skoku ani samo neurčuje platnost či přešlap.",
      featureFourTag: "KONTROLA OBSLUHY",
      officialsEyebrow: "PRO ROZHODČÍ",
      officialsTitle: "Druhý pohled<br><em>před dalším skokem.</em>",
      officialsText: "Soutěž pokračuje a sporné odrazy dostanou pozornost, kterou si zaslouží.",
      officialsLink: "Prohlédnout licenci <span>→</span>",
      clubsEyebrow: "PRO KLUBY A TRENÉRY",
      clubsTitle: "Technickou kontrolu<br><em>opakujte stejně.</em>",
      clubsText: "Použijte stejné ovládání pro trénink, přípravu závodů i zpětnou vazbu závodníkům.",
      clubsLink: "Stáhnout pro Windows <span>→</span>",
      screensEyebrow: "STANOVIŠTĚ V KOSTCE",
      screensTitle: "Soustředěný pohled<br><em>v rozhodující chvíli.</em>",
      screensLead: "Zvolte kontrastní tmavý nebo čistý světlý motiv podle místnosti, obrazovky a obsluhy.",
      offerEyebrow: "ÚVODNÍ NABÍDKA",
      offerTitle: "Jedno stanoviště.<br><em>Jedna jasná licence.</em>",
      offerLead: "Trvalá licence pro jeden počítač s Windows včetně instalátoru pro Windows a e-mailové podpory.",
      offerItemOne: "Trvalá licence pro jeden počítač",
      offerItemTwo: "Instalátor pro Windows",
      offerItemThree: "Anglické a české rozhraní",
      offerItemFour: "E-mailová podpora vývojáře",
      priceKicker: "LONGJUMPREPLAY 3.1",
      priceNote: "jeden počítač s Windows · trvalá licence",
      priceButton: "Požádat o licenci <span>↗</span>",
      priceFootnote: "Bez online účtu. Bez nahrávání do cloudu. Pro aktivační klíč nám pošlete kód počítače.",
      downloadEyebrow: "PŘIPRAVENO",
      downloadTitle: "Nainstalujte stanoviště rozhodčího.",
      downloadLead: "Instalátor umístí LongJumpReplay do Program Files a přidá běžnou položku do nabídky Start. Záznamy a nastavení zůstanou ve vašem uživatelském profilu.",
      downloadButton: "Stáhnout instalátor <span>↓</span>",
      checksum: "Kontrolní součet SHA-256 <span>↗</span>",
      contactEyebrow: "PROMLUVME SI O VAŠEM NASTAVENÍ",
      contactTitle: "Jasnější rozhodnutí<br><em>u pískoviště.</em>",
      contactText: "Napište nám o své kameře, formátu závodu nebo klubovém provozu. Odpovíme s dalším postupem a aktivací pro váš počítač.",
      footerNote: "Živý záznam · přesná kontrola · kontrola obsluhy"
    }
  };

  let language = localStorage.getItem("ljr-language") || "en";
  let currentStep = 0;
  const byId = (id) => document.getElementById(id);

  const stateWords = {
    en: ["RUNWAY", "FREEZE", "REPLAY", "DECIDE"],
    cs: ["DRÁHA", "ZMRAZIT", "PŘEHRÁT", "ROZHODNOUT"]
  };

  const renderStep = () => {
    const word = document.querySelector(".stage-word");
    if (word) word.textContent = stateWords[language][currentStep];
    const label = document.querySelector(".timeline-freeze");
    if (label) label.textContent = language === "cs" ? "BOD ZMRAZENÍ" : "FREEZE POINT";
  };

  const setLanguage = (next) => {
    language = next;
    document.documentElement.lang = next;
    document.querySelectorAll("[data-copy]").forEach((node) => {
      const value = copy[next][node.dataset.copy];
      if (value !== undefined) node.innerHTML = value;
    });
    const languageButton = byId("languageToggle");
    languageButton.textContent = next === "en" ? "CZ" : "EN";
    languageButton.setAttribute("aria-label", next === "en" ? "Switch to Czech" : "Přepnout do angličtiny");
    renderStep();
    localStorage.setItem("ljr-language", next);
  };

  const applyTheme = (theme) => {
    document.documentElement.dataset.theme = theme;
    const button = byId("themeToggle");
    const light = theme === "light";
    button.textContent = light ? "☾" : "☼";
    button.setAttribute("aria-label", light ? "Switch to dark theme" : "Switch to light theme");
  };

  const email = config.contactEmail || "xpisar10@gmail.com";
  byId("price").textContent = config.price || "4 990 Kč";
  byId("version").textContent = `Windows installer · v${config.versionLabel || "3.1.0"}`;
  byId("downloadLink").href = config.installerUrl || "#";
  byId("checksumLink").href = config.checksumUrl || "#";

  const subject = encodeURIComponent("LongJumpReplay license inquiry");
  const body = encodeURIComponent("Hello,\n\nI would like to ask about a LongJumpReplay license.\n\nCustomer / organization:\nMachine code (if available):\n\nThank you.");
  const mailto = `mailto:${email}?subject=${subject}&body=${body}`;
  byId("emailLink").href = mailto;
  byId("buyLink").href = mailto;

  byId("languageToggle").addEventListener("click", () => setLanguage(language === "en" ? "cs" : "en"));
  byId("themeToggle").addEventListener("click", () => {
    const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
    localStorage.setItem("ljr-theme", next);
    applyTheme(next);
  });
  document.querySelectorAll(".workflow-step").forEach((button) => button.addEventListener("click", () => {
    currentStep = Number(button.dataset.step);
    document.querySelectorAll(".workflow-step").forEach((step) => step.classList.remove("is-active"));
    button.classList.add("is-active");
    renderStep();
  }));

  applyTheme(localStorage.getItem("ljr-theme") || "dark");
  setLanguage(language);
})();
