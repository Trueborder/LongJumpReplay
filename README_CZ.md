# Long Jump Replay 3.1 – český návod

Program slouží pro živý náhled a zpětnou kontrolu odrazu při skoku dalekém. Kamera běží dál i během kontroly pokusu. Zmrazený pokus se uloží jako samostatný dočasný záznam, takže po přepsání živého bufferu nezmizí.

## Režim pro slabší počítače

Na starším nebo méně výkonném počítači v nastavení Výkon zvolte **Režim pro slabší PC**. Kamera zůstane nastavena na požadovanou frekvenci, ale aplikace vykresluje rozhraní při 20 Hz, ukládá každý druhý snímek (60 FPS z kamery 120 FPS), používá 15sekundový živý buffer a nejvýše 1 GB RAM.

V hlavním záhlaví je také viditelné tlačítko **Pozastavit systém**. Vypne kameru, zastaví živý záznam, vymaže živý RAM buffer a zablokuje rozhodování i časomíru. Již dokončené pokusy zůstanou zachovány. Tlačítko **Obnovit systém** znovu připojí kameru a začne s prázdným živým bufferem.

Stránka Kamera v nastavení zobrazuje běžný rozevírací seznam s názvy zařízení Windows, například `0 · Integrated Camera` nebo `1 · OBS Virtual Camera`. Úvodní číslo zůstává indexem OpenCV uloženým v konfiguraci. Po připojení nové kamery znovu otevřete Nastavení a po změně kamery restartujte aplikaci.

## Nejdůležitější změna

Po stisku mezerníku vznikne pokus se stavem **Nerozhodnuto**. Dalším stiskem mezerníku se vrátíš na živý obraz a program může automaticky přejít k dalšímu závodníkovi. Není nutné označit každý pokus jako Platný, Přešlap nebo Kontrola.

Povinné rozhodování lze zapnout:

```text
Nastavení → Pokusy a rozhodnutí → Vyžadovat rozhodnutí před pokračováním
```

## Pořadí pokusů

Při osmi závodnících a třech pokusech:

```text
1. kolo: 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8
2. kolo: 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8
3. kolo: 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8
```

Volitelné finále může obsahovat Top 8, 10, 12 nebo vlastní počet a další tři pokusy. Finalisté se vybírají ručně, protože program neměří délku skoku.

## První spuštění

1. Spusť `RUN_SYNTHETIC.bat`.
2. Otevři **Spustit průvodce soutěží**.
3. Vyber správu soutěže, nebo režim pouze rozhodčího.
4. Nastav závodníky, pokusy, kameru a výkonový profil.
5. Pro skutečnou kameru použij `RUN_CAMERA.bat`.

## Výkon

V Nastavení je pět profilů:

- Quiet / Low-power – slabší počítače a nižší hluk ventilátoru;
- Balanced – doporučené výchozí;
- High performance – výkonnější počítače;
- Evidence – podrobnější náhled a analýza;
- Custom – vlastní hodnoty.

Každá náročná volba má označení **Nízký / Střední / Vysoký / Velmi vysoký dopad**. Snížení FPS náhledu nesnižuje FPS záznamu kamery.

## Sdílení jako Windows aplikace

Kompletní zákaznickou verzi vytvoří jediný příkaz:

```text
BUILD_CUSTOMER_RELEASE.bat
```

Po úspěšných testech skript nahradí celý obsah složky `release` a vloží do ní instalátor 3.1 s kontrolním součtem, nasaditelný web se stejným instalátorem, zákaznickou dokumentaci a souhrnný soubor `SHA256SUMS.txt`. Soukromý licenční klíč ani nástroj pro správu licencí se do zákaznické verze nekopírují.

Pouze pro přenosnou záložní variantu spusť:

```text
BUILD_PORTABLE.bat
```

Výsledek:

```text
release\LongJumpReplay-3.1-Windows-x64.zip
```

Příjemce ZIP jen rozbalí a spustí `LongJumpReplay.exe`. Python nepotřebuje.

Když je vybraná soutěžní tabule, obyčejné šipky vždy přecházejí mezi buňkami a neposouvají snímky bez ohledu na aktivní prvek. Enter otevře nebo vybere buňku, mezerník vždy ovládá Zmrazit/Živě. Po zmrazení zůstane modrý rámeček na právě hodnoceném pokusu a na dalšího závodníka se přesune až po návratu na Živě. Pravé tlačítko nabízí všechny varianty rozhodnutí i nad prázdnou dostupnou buňkou; takový výsledek se uloží bez videa. Smazání je dostupné, až když buňka obsahuje záznam. Panel dalšího pokusu je přímo nad tabulí; původní seznam Chlapci/Dívky a tlačítka Předchozí/Další byly odstraněny.

V Nastavení má každá volba vlastní popis. Přepínač Zobrazovat popisy nastavení okamžitě skryje nebo obnoví celý sloupec popisů. Tlačítka a rozbalovací seznamy používají kompaktní zaoblený vzhled a zaškrtávací políčka mají jasně viditelný kruhový indikátor.

Podrobný anglický návod je v `README.md` a výsledky testů v `TEST_REPORT_3.1.md`.
