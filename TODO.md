# TorBox Media Center TODO

Scope: server-side work in this repository for the Jellyfin scan-triggered
refresh integration. Plugin-only work lives in the standalone plugin repo:

- Repo: https://github.com/DanCorley/jellyfin-plugin-torbox-refresh
- Plugin TODO: https://github.com/DanCorley/jellyfin-plugin-torbox-refresh/blob/main/TODO.md

Items below call out the plugin task they unblock so the two TODOs stay in sync.

## Current state

- [x] Authenticated `POST /refresh` and `GET /health` in `functions/controlServer.py`.
- [x] Control API v2: `GET /health` reports `api_version: 2`; async `POST /refresh/jobs` and `GET /refresh/jobs/{id}` with `queued|running|completed|failed`.
- [x] Synchronous `POST /refresh` retained for plugin 1.0.0 compatibility.
- [x] `Idempotency-Key` replay on `POST /refresh/jobs` and 20-job result retention.
- [x] Staged API fetch, per-type TinyDB replacement, shared refresh lock.
- [x] Atomic `.strm` reconciliation with added/removed/updated counts.
- [x] On-demand FUSE VFS refresh and startup-race fix.
- [x] Python regression tests for refresh staging, diffing, `.strm` writes/cleanup, control auth, async jobs, idempotency, cooldown, conflicts and retention.
- [x] `.dockerignore` excludes `.env`, `config/`, `torbox/` and local compose data.
- [x] Changes are on `feat/jellyfin-refresh-control-api`.
- [x] Plugin was split into its own repository.
- [x] README and `docker.md` document the v2 contract, compatibility matrix and troubleshooting.
- [x] Docker healthcheck for `/health` and compose log rotation.

## Release and repository

- [ ] `TMC-REL-1` Decide whether to upstream the feature branch to `TorBox-App/torbox-media-center` or keep it in the fork.
- [x] `TMC-REL-2` Point `.github/workflows/docker-build.yml` at your own image namespace; it now publishes to `ghcr.io/${{ github.repository }}` with Docker Hub optional.
- [ ] `TMC-REL-3` Keep personal deployment files out of an upstream PR; use a local compose override.
- [ ] `TMC-REL-4` Pin production image tags and publish a TMC release that contains the control API. Unblocks `PLG-REL-3` and `PLG-DOC-4`.
- [x] `TMC-REL-5` Add the supported-plugin/API compatibility statement to the TMC README. Unblocks `PLG-DOC-4`.

## API contract

- [x] `TMC-API-1` Add a `CONTROL_API_VERSION` constant (`2`) and return it from `GET /health`. The plugin checks it before choosing async jobs; TMC itself does not reject unsupported clients. Unblocks `PLG-H-13`.
- [x] `TMC-API-2` Add an async refresh job API alongside the synchronous endpoint:
  - [x] `POST /refresh/jobs` returns `202 {job_id, status, status_url}`.
  - [x] `GET /refresh/jobs/{job_id}` returns `queued|running|completed|failed` plus counts/errors.
  - [x] Keep one active job; return `409` with `job_id`/`active_job_id` while busy.
  - [x] Retain the last 20 finished job results for diagnostics.
  - [x] Keep synchronous `POST /refresh` returning `200` for plugin 1.0.0.
  - Unblocks `PLG-H-5`.
- [x] `TMC-API-3` Add `Idempotency-Key` request dedupe for repeated scan triggers; replays return `202` for the existing job.
- [x] `TMC-API-4` Document the control API contract (endpoints, status codes, response schema, idempotency, retention). Unblocks `PLG-H-14`.

## Security

- [x] `TMC-SEC-1` Bearer token with constant-time comparison.
- [x] `TMC-SEC-2` Keep the control API on a private Docker network; document that `8787` must not be published.
- [x] `TMC-SEC-3` Add TLS/reverse-proxy guidance for cross-host deployments.
- [x] `TMC-SEC-4` Do not reuse the TorBox API key as the control token.
- [ ] `TMC-SEC-5` Add structured logs with refresh duration, counts, partial failures and request IDs; never log tokens or API keys. Duration/counts/job IDs are logged; request IDs are still missing.
- [x] `TMC-SEC-6` Support Docker secrets or restricted env files; keep secrets out of Git and images. Documented via an entrypoint wrapper because the app reads env vars.
- [x] `TMC-SEC-7` Document the existing TorBox API-key exposure in `.strm` files as an accepted design constraint.
- [x] `TMC-SEC-8` Add a non-root mode for `strm` deployments (FUSE still needs `/dev/fuse` and `SYS_ADMIN`). Documented through compose `user:`; not enabled by default.

## Reliability and observability

- [x] `TMC-OPS-1` Add a Docker healthcheck for `/health`.
- [x] `TMC-OPS-2` Add log rotation for the TMC container.
- [ ] `TMC-OPS-3` Add integration tests for partial API failure, TMC restart and concurrent scan/refresh. Partial API failure is covered by `tests/test_integration_refresh.py`; restart and concurrent scan/refresh are not.
- [x] `TMC-OPS-4` Add a fake TorBox API mode or fixture so CI does not hit the real API (`tests/fake_torbox_api.py`).
- [ ] `TMC-OPS-5` Monitor refresh duration, failure counts and `last_error`. `/health` and logs expose the fields; no monitoring stack is configured.
- [x] `TMC-OPS-6` Decide whether to expose a `/metrics` endpoint. Decision: no `/metrics`; scrape `/health` and container logs.
- [x] `TMC-OPS-7` Document upgrade order (TMC first, then plugin) and rollback.
- [x] `TMC-OPS-8` Keep `.env`, `config/`, `torbox/` and local compose files out of the image and Git.

## Documentation

- [x] `TMC-DOC-1` Add a network diagram showing Jellyfin, TMC and the control API.
- [x] `TMC-DOC-2` Document token generation and rotation.
- [x] `TMC-DOC-3` Document the `CONTROL_MIN_INTERVAL` and plugin cooldown interaction.
- [x] `TMC-DOC-4` Document the metadata-enabled slow-refresh case and how to raise the plugin timeout.
- [x] `TMC-DOC-5` Document FUSE requirements (mount visibility and propagation).
- [x] `TMC-DOC-6` Maintain the compatibility matrix with the plugin repo. Unblocks `PLG-DOC-4`.
- [x] `TMC-DOC-7` Add TMC release and upgrade notes.

## Cross-repo dependency map

| TMC task | Plugin task it unblocks | Why |
|---|---|---|
| `TMC-API-1` | `PLG-H-13` | Plugin can check the control API version before calling it. |
| `TMC-API-2` | `PLG-H-5` | Plugin can poll a job instead of holding a long HTTP request. |
| `TMC-API-4` | `PLG-H-14` | Plugin client and docs use the documented response schema. |
| `TMC-REL-4` | `PLG-REL-3`, `PLG-DOC-4` | Plugin release notes and compatibility matrix reference a released TMC version. |
| `TMC-DOC-6` | `PLG-DOC-4` | One compatibility matrix for both repositories. |
| `TMC-DOC-1`, `TMC-DOC-3`, `TMC-DOC-4`, `TMC-DOC-5` | `PLG-DOC-1`, `PLG-DOC-3` | Plugin setup/troubleshooting links to TMC deployment docs. |
