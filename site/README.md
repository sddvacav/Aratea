# site/

Public landing page for Augure. Single-file HTML, no build step.

**Live:** [augure.vercel.app](https://augure.vercel.app/)

## Files

- `index.html` — the landing. Bilingual (FR/EN) with IP-based language detection on first visit, language preference persisted in `localStorage`. Four CTAs: Discord, GitHub, Dashboard, Notion whitepaper.

## Edit

Public links live at the top of the inline `<script>` (`const LINKS = {...}`). i18n strings are in the `I18N` object below it.

The Notion white paper link is **language-aware**: `LINKS.notion` is an object `{ fr, en }`. The active URL is set inside `applyLang()` so visitors are sent to the page in their detected/selected language.

## Deploy

Deployed on Vercel as a static site. The project is git-linked to `Elladriel80/augure` with **Root Directory** = `site/` and no build command — every push to `main` redeploys automatically.

The companion read-only dashboard (Phase 1 on-chain state) lives in `../dashboard/` and is deployed at [augure-app.vercel.app](https://augure-app.vercel.app/).
