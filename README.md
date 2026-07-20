# Face Fit

Face Fit is a Korean AI interview practice prototype. It guides a candidate from interview setup to environment calibration, a live interview, analysis, report, and growth history.

## Included flows

- Interview setup with interviewer personas and intensity
- Equipment check using a real camera-preview asset, face frame, eye-level line, shoulder line, device selectors, and microphone test
- Voice profile guide: guide → recording → review → preparation complete
- Interview room, analysis state, report, and my page
- Interactive prototype controls for menus, tabs, buttons, device selectors, recording states, and notification panels

The current voice profile flow is a front-end prototype. It does not save audio or perform voice cloning.

## Local development

Requirements: Node.js 24 or later.

```bash
npm ci
npm run dev
```

Open `http://localhost:3000`.

## Quality checks

```bash
npm run lint
npm run typecheck
npm run build
```

## Deploy to Vercel

1. Create an empty GitHub repository under your own account.
2. Replace the template remote with that repository URL.
3. Push the `release/uiux-mentoring` branch.
4. Import the repository at [Vercel](https://vercel.com/new). Vercel detects Vite from `vercel.json`.
5. Use `npm run build` and the `dist` output directory. The included SPA rewrite makes direct route access resolve to `index.html`.

No environment variables are required for this front-end prototype.

## Design review artifacts

The UI/UX mentoring HTML, matching PDF, and source screenshots are review inputs and are intentionally excluded from this application repository. The complete pre-development planning set, OpenAvatarChat + MuseTalk integration plan, QA criteria, and traceability are indexed in [`docs/product/README_FaceFit_기획산출물.md`](docs/product/README_FaceFit_기획산출물.md).

## Project structure

```text
src/main.tsx          Vite entry point
src/App.tsx           BrowserRouter route map
src/pages/            Route-level screen components
src/components/       Shared Face Fit UI
src/lib/              Shared content and helpers
public/images/        Product images used by the prototype
```

## Docker

`docker compose up app` builds the Vite bundle with Node 24 and serves it from Nginx on port `3000` by default. The Nginx configuration includes SPA route fallback, so direct visits to routes such as `/session/live` work in production.
