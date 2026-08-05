# FaceFit API implementation status

Reference: `FaceFit_백엔드_API_명세서_v0.3.md` v0.3.6

## Contract source of truth

- OpenAPI 3.1: `openapi/facefit-api.phase1.yaml`
- Generated TypeScript: `src/api/generated/facefit.ts`
- Generate and verify: `npm.cmd run api:check`

The filename is retained for compatibility. The OpenAPI file now covers every public endpoint in the specification, including the server OAuth callback and MEDIA-003 Range streaming.

## Implemented frontend contract slices

- AUTH-001 to AUTH-006, LEGAL-001 to LEGAL-002, ONBOARDING-001, MEMBER-001
- DOC-001 to DOC-005, JOB-001 to JOB-005, SESSION-001 to SESSION-006
- SESSION-004/SESSION-005, QUESTION-001/QUESTION-002, ANSWER-001/ANSWER-002
- ANALYSIS-001/ANALYSIS-002, REPORT-001, AUDIO-001, HISTORY-001, GROWTH-001
- LEGAL-003/LEGAL-004/LEGAL-005, MEMBER-002/MEMBER-003, MEDIA-001/MEDIA-002/MEDIA-003, VOICE-001/VOICE-002/VOICE-003, SESSION-006, ANSWER-003, TELEMETRY-001, CONTEXT-001, VAD stop control, IndexedDB answer outbox

The client has an environment-based API origin, JSON envelope parser, in-memory access token, refresh single-flight, GET/binary 401 retry, multipart upload, idempotency-key generation, and retry-aware polling.

Implemented routes include `/source-resources`, `/sessions/:sessionId/settings`, `/sessions/:sessionId/live`, `/sessions/:sessionId/analysis`, and `/sessions/:sessionId/report`.

## Contract corrections applied on 2026-08-05

1. QUESTION-002 returns `PlaybackAccess`; MP4 Range streaming remains MEDIA-003.
2. VOICE-001 uses `consentLegalRecordId`.
3. All JSON errors use the flat section 12.3 envelope.
4. AUDIO-001 `202` uses the section 12.3 success envelope with `data: { status: "PROCESSING", retryAfterSec }`; it is no longer an exception to the JSON envelope contract.
5. LEGAL-005 was added because LEGAL-004 requires `consentRecordId`, while a fresh browser session otherwise has no way to recover active consent records for revocation.

## Verification and remaining external work

1. `npm.cmd run api:check` regenerates the OpenAPI types and runs TypeScript verification.
2. `npm.cmd run test` covers retry-aware polling, idempotency-key generation, and success/error JSON envelopes.
3. `npm.cmd run check` runs lint, type-checking, and a production build.
4. A live browser E2E run remains dependent on a deployed backend test environment with OAuth test credentials and seeded owned resources. It must exercise the real CORS, refresh-cookie, multipart upload, Range-streaming, and deletion workers; these cannot be truthfully simulated by the frontend repository alone.
5. `npm.cmd audit fix` updated 33 packages without a major-version change. The unused `shadcn` runtime package and its CSS import were removed, eliminating 286 transitive packages and the Hono-related findings.
6. `npm.cmd audit` now reports two high React Router findings. NPM offers only `npm audit fix --force`, which downgrades `react-router-dom` from 7.18 to 7.11 and is marked as breaking; it was deliberately not applied without a compatibility decision.

Any new route or contract adjustment must be recorded in both the API specification and this file before frontend/backend implementation.
