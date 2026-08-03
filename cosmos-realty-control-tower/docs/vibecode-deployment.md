# Bitrix24 VibeCode deployment

## Purpose

VibeCode is a thin hosting and user-interface layer for the existing Cosmos Realty Control Tower. The Python rules engine, reports, calibration and business definitions remain canonical. The embedded app reads safe aggregates and displays previews; it does not implement or execute CRM write actions.

## Current safety boundary

- Every control rule remains `DRY_RUN`.
- The app has no route that changes leads, deals, tasks, chats or Disk.
- `VIBE_APP_KEY` and `VIBE_API_KEY` are read only from the process environment.
- The repository contains examples, never real keys or session tokens.
- Server access policy stays `OWNER_ONLY` until the owner explicitly approves broader employee access.

## Required application scopes

Minimum for the first embedded version: `crm`, `task`, `user`, `department`, and `placement`. Add `im` and `disk` only when a reviewed read-only feature actually needs chats or files. The application key must start with `vibe_app_`; a personal `vibe_api_` key cannot bind placements.

## Black Hole preparation

The prepared manifest is `vibecode-app/deploy.example.json`. It selects the trial-compatible `bc-micro` plan and keeps `OWNER_ONLY`. Before creating a paid resource, confirm the current price in `/v1/me` or the provider plan endpoint and obtain owner approval.

Deployment prerequisites:

1. Create an application authorization key in VibeCode with the minimum scopes above.
2. Store it locally as `VIBE_APP_KEY`; do not paste it into GitHub, a PR, or logs.
3. Run `scripts/vibecode_preflight.sh`.
4. Run the local tests and start the app with `npm start` from `vibecode-app`.
5. Create the Black Hole server only after explicit cost approval.
6. Deploy the repository artifact with the manifest settings and upload `icon.svg` to `/_gw/icon`.
7. Read available placements live with `GET /v1/placements/available`.
8. Bind the actual Menu code and `CRM_LEAD_DETAIL_TAB`; do not guess codes.
9. Verify the placement list and open both interfaces as a non-owner employee before changing access policy.

## Authentication flow

Black Hole Gateway authenticates the Bitrix24 employee and injects `X-Vibe-Authorization: Bearer vibe_session_...`. The server forwards that session to VibeCode together with the application key. The session is never exposed to browser JavaScript. The app also reads the sanitized user ID and role headers for display/audit context.

## Lead card placement

The lead ID comes from `placement_options`, not from the Bitrix24 JavaScript SDK. The first version displays the card ID, control status, violations, next-step evidence and a link to the full report. Until the existing rules engine produces evidence for that card, the status is `REVIEW_REQUIRED`; missing data is never interpreted as a violation.

## Publication blockers

- A `vibe_app_` key with `placement` scope is required.
- The portal must satisfy VibeCode's Marketplace/commercial placement prerequisite.
- Creating `bc-micro` requires explicit approval of the confirmed monthly/sleep price.
- Employee access requires an explicit access-policy decision after owner-only verification.

Official references: [application runtime](https://vibecode.bitrix24.tech/docs-content/infra/app-runtime.md), [placements](https://vibecode.bitrix24.tech/docs-content/apps/placements.md), [applications](https://vibecode.bitrix24.tech/docs-content/apps.md).
