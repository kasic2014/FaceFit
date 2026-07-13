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
npm install
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
4. Import the repository at [Vercel](https://vercel.com/new). Vercel detects Next.js automatically.
5. Leave the build command as `npm run build` and the output setting as the default.

No environment variables are required for this front-end prototype.

## Design review artifacts

The workspace root contains `uiux멘토링화면설계서.html`. The matching PDF and the source screenshots are stored under the workspace-level `deliverables/uiux-mentoring/` folder; these are intentionally excluded from the application repository.

## Project structure

```text
src/app/              Route-level screens
src/components/       Shared Face Fit UI
src/lib/              Shared content and helpers
public/images/        Product images used by the prototype
```
