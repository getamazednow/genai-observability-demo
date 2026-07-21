# GenAI Project Observability — Design System Localisation

> Localises the portable **Getamazednow AI Design System v1.2** (vendored at `Getamazednow AI Design System v1.2/`, see its `LOCALISE.md`) for this project. Brand tokens are consumed **unchanged**; only the points below are project-specific. This note lives in the project root by design — the design-system folder stays byte-identical to the master.

## 1. Artefact / product name

**GenAI Project Observability** — a reference architecture and demo dashboard for observing agentic Gen AI workflows in production, built for architecture-board, risk-committee and Community-of-Practice review ahead of a real Datadog implementation.

Shown as:

- Web topbar / dashboard: `Getamazednow AI · GenAI Project Observability`
- Running headers (Word): `Getamazednow AI · GenAI Observability Training Guide · v1.2`
- Presentation footers: `Getamazednow AI · A Getamazednow Company` alongside the deck title and slide number
- Covers: the title beneath the logo lockup

Artefacts in scope (training folder):

- `training/docx/GenAI-Observability-Training-Guide.docx`
- `training/slides/GenAI-Observability-Exec-Overview.pptx`
- `training/slides/GenAI-Observability-Technical-Deepdive.pptx`

## 2. Version + status

Current cycle: **v1.1 → v1.2** (design-system re-skin — additive presentation/whitepaper cover layer). Status line on every cover/footer: **MOCK / PORTFOLIO REFERENCE — NOT CONNECTED TO ANY LIVE SYSTEM** (this project's mandatory "synthetic data" disclaimer, carried in addition to the standard DRAFT / FOR PEER REVIEW / FINAL states — here: **FINAL** for demo distribution). Version lives inside the document (cover + footer), not in file/folder names.

## 3. Legacy colour remap

**N/A for palette** — the training artefacts were already authored on the Getamazednow AI palette (Ink `#2A363B`, Signal `#5FA8CC`, signalDeep `#2E7DA6`, the shared neutrals and semantics) with Poppins/Inter type. The v1.2 re-skin is therefore **additive**: it applies the new Tensor-lattice cover/background image assets and the §8 presentation lockup + footer identity rather than remapping colours.

Project cover/background image assets (complement the design-system logo files — kept dark-toned / light-toned so a reversed logo and title stay legible per §7/§8 hybrid-image rule):

| Asset | Tone | Applied to |
|---|---|---|
| `GenAIObsPPT-1.jpg` | Dark Ink, globe right | Deck title (alt) |
| `GenAIObsPPT-2.jpg` | Dark Ink, wave + globe right | Deck title slide |
| `GenAIObsPPT-3.jpg` | Light, lattice + dashboard | Light content accent (optional) |
| `GenAIObsPPT-4.jpg` | Dark teal, rings + globe right | Section divider slides |
| `GenAIObsPPT-5.jpg` | Dark Ink, bar-chart + globe | Closing / data slides |
| `GenAIObsDOC-1.jpg` | Light vertical panels | Word cover (W2 lower hero) |
| `GenAIObsDOC-2.jpg` | Light horizontal bands | Word cover band (alt) |

Fonts: legacy substitutes → **Poppins** (display/heading) / **Inter** (body). Office fallback Montserrat/Segoe UI applies only where the fonts aren't installed.

## 4. Reference implementation

The re-skinned training artefacts above **are** this project's reference implementation of the system: they show the §8 presentation masters (P2 corner + topic image on the title, Tensor-lattice section dividers, quiet-footer content slides) and the §7 W2 whitepaper cover applied to a real board-grade deliverable. The live dashboard (`dashboard/index.html`) is the §6 web-page reference.

---

*Source of truth for brand + application rules: `Getamazednow AI Design System v1.2/` (`design-tokens.json`, `Artefact-Application-Spec.md`, `LOCALISE.md`). This note localises it for **GenAI Project Observability** only.*
