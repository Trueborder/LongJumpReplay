# Long Jump Replay 2.3 – český návod

Program slouží pro živý náhled a zpětnou kontrolu odrazu při skoku dalekém. Kamera běží dál i během kontroly pokusu. Zmrazený pokus se uloží jako samostatný dočasný záznam, takže po přepsání živého bufferu nezmizí.

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

Spusť:

```text
BUILD_PORTABLE.bat
```

Výsledek:

```text
release\LongJumpReplay-2.3-Windows-x64.zip
```

Příjemce ZIP jen rozbalí a spustí `LongJumpReplay.exe`. Python nepotřebuje.

Podrobný anglický návod je v `README.md` a výsledky testů v `TEST_REPORT_2.3.md`.
