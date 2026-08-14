# Tomáš Pisár — Design System

Generated with UI/UX Pro Max on 2026-08-12, then refined after the initial generic portfolio match failed the project-specific design critique.

## Product and audience

- Independent developer portfolio and LongJumpReplay sales site.
- Primary audiences: sports officials, club operators, Windows users evaluating the product, and people seeking support.
- Primary job: establish trust, explain the Capture → Freeze → Replay → Decide workflow, and make the product/download path obvious.

## Direction: Evidence Desk

The visual language comes from replay stations, timing displays, take-off boards, and track-side decision making. It should feel precise and calm under pressure—not like a generic developer terminal or a sports-team fan site.

### Signature

Use one take-off-line/timecode motif in the main hero. Elsewhere, prefer quiet rules and evidence labels. Do not repeat decorative grids, oversized numbers, or numbered cards unless order genuinely matters.

## Tokens

### Dark theme

| Role | Value | Meaning |
|---|---:|---|
| Background | `#0B1013` | Timing black |
| Soft background | `#10171B` | Track lane |
| Surface | `#151E23` | Evidence panel |
| Surface raised | `#1B282E` | Review panel |
| Text | `#F3F0E8` | Chalk |
| Muted text | `#A7B3B4` | Steel |
| Border | `#34444A` | Lane rule |
| Live | `#62D9C6` | Capture cyan |
| Review | `#EFB84F` | Decision amber |
| Warning | `#E56D54` | Foul-line coral |

### Light theme

| Role | Value |
|---|---:|
| Background | `#F2F0E9` |
| Surface | `#FBFAF6` |
| Text | `#11191C` |
| Muted text | `#58676B` |
| Border | `#BCC9C7` |
| Live | `#087F70` |
| Review | `#9C5D08` |
| Warning | `#A74231` |

### Typography

- Display: Barlow Condensed 500/600/700 — selected from the skill's Sports/Fitness match for athletic, condensed headlines.
- Body: Barlow 400/500/600 — same family for calm, readable continuity.
- Utility/data: DM Mono 400/500 — timecodes, labels, versions, and technical metadata only.
- Body copy: 16px minimum, 1.65 line height, maximum 66 characters where practical.

### Spacing

Use an 8px base: 8, 16, 24, 32, 48, 64. Sections may expand responsively but components stay on this rhythm.

## Components

- Buttons are rectangular and at least 44px high. One cyan primary action per decision area; amber is hover/review feedback, not a competing CTA.
- Cards are flat evidence panels with rules, not floating rounded tiles. Use a colored edge only to communicate role.
- Screenshots reserve their aspect ratio, include descriptive alt text, and open in a keyboard-operable native dialog.
- Navigation highlights the current page and collapses into a labeled, keyboard-operable mobile menu.
- Workflow numbers are allowed only for Capture, Freeze, Replay, Decide and installation steps because order carries meaning.

## Motion

- One restrained hero entrance: opacity + 12px translate, 420ms or less.
- Interaction transitions: 150–280ms using color, opacity, and transform only.
- Respect `prefers-reduced-motion`; content must remain visible without JavaScript.

### Apple-inspired refinement (2026-08-13)

- Keep the Evidence Desk vocabulary—live cyan, decision amber, take-off line, timecode, and real station screenshots—but use Apple-like restraint in the shell.
- The shared site header is a translucent material with a stronger surface after scrolling; mobile navigation opens from its anchor with opacity and a short scale/translation.
- Product and evidence surfaces use 18–24px radii, thin semantic borders, restrained shadow, and no decorative blur where it harms legibility. Reduced transparency replaces glass with solid surfaces.
- The page uses system-ui for readable body copy while retaining Barlow Condensed for the athletic display voice and DM Mono for evidence metadata.
- Scroll reveals are limited to opacity/translate, 150–420ms, and are disabled when reduced motion is requested. Core content remains visible without JavaScript.

## Accessibility and delivery rules

- Maintain WCAG AA contrast, visible focus, semantic headings, and skip navigation.
- Interactive targets are at least 44×44px with 8px separation where practical.
- Use inline SVG for interface icons; never rely on emoji or color alone.
- Preserve browser zoom and avoid horizontal scrolling at 375, 768, 1024, and 1440px.
- English and Czech content must remain complete and UTF-8 safe.
