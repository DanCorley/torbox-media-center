# TorBox Media Center TODO

Scope: server-side work in this repository for the Jellyfin scan-triggered
refresh integration. Plugin-only work lives in the standalone plugin repo:

- Repo: https://github.com/DanCorley/jellyfin-plugin-torbox-refresh
- Plugin TODO: https://github.com/DanCorley/jellyfin-plugin-torbox-refresh/blob/main/TODO.md

Items below call out the plugin task they unblock so the two TODOs stay in sync.

## Current state

- [x] Authenticated `POST /refresh` and `GET /health` in `functions/controlServer.py`.
- [x] Staged API fetch, per-type TinyDB replacement, shared refresh lock.
- [x] Atomic `.strm` reconciliation with added/removed/updated counts.
- [x] On-demand FUSE VFS refresh and startup-race fix.
- [x] Python regression tests for refresh staging, diffing, `.strm` writes/cleanup and control auth.
- [x] `.dockerignore` excludes `.env`, `config/`, `torbox/` and local compose data.
- [x] Changes are on `feat/jellyfin-refresh-control-api`.
- [x] Plugin was split into its own repository.

## Release and repository

- [ ] `TMC-REL-1` Decide whether to upstream the feature branch to `TorBox-App/torbox-media-center` or keep it in the fork.
- [ ] `TMC-REL-2` Point `.github/workflows/docker-build.yml` at your own image namespace; it currently pushes to `anonymoussystems/...` and `ghcr.io/torbox-app/...`.
- [ ] `TMC-REL-3` Keep personal deployment files out of an upstream PR; use a local compose override.
- [ ] `TMC-REL-4` Pin production image tags and publish a TMC release that contains the control API. Unblocks `PLG-REL-3` and `PLG-DOC-4`.
- [ ] `TMC-REL-5` Add the supported-plugin/API compatibility statement to the TMC README.

## API contract

- [ ] `TMC-API-1` Add a `CONTROL_API_VERSION` constant and return it from `GET /health`; warn or reject unsupported plugin versions. Unblocks `PLG-H-13`.
- [ ] `TMC-API-2` Replace the synchronous `POST /refresh` with an async job:
  - [ ] `POST /refresh` returns `202 {job_id}`.
  - [ ] `GET /refresh/{job_id}` returns `queued|running|completed|failed` plus counts/errors.
  - [ ] Keep one active job; return `409` while busy.
  - [ ] Retain the last N job results for diagnostics.
  - Unblocks `PLG-H-5`.
- [ ] `TMC-API-3` Add an idempotency key or request dedupe for repeated scan triggers.
- [ ] `TMC-API-4` Document the control API contract (endpoints, status codes, response schema). Unblocks `PLG-H-14`.

## Security

- [x] `TMC-SEC-1` Bearer token with constant-time comparison.
- [ ] `TMC-SEC-2` Keep the control API on a private Docker network; document that `8787` must not be published.
- [ ] `TMC-SEC-3` Add TLS/reverse-proxy guidance for cross-host deployments.
- [ ] `TMC-SEC-4` Do not reuse the TorBox API key as the control token.
- [ ] `TMC-SEC-5` Add structured logs with refresh duration, counts, partial failures and request IDs; never log tokens or API keys.
- [ ] `TMC-SEC-6` Support Docker secrets or restricted env files; keep secrets out of Git and images.
- [ ] `TMC-SEC-7` Document the existing TorBox API-key exposure in `.strm` files as an accepted design constraint.
- [ ] `TMC-SEC-8` Add a non-root mode for `strm` deployments (FUSE still needs `/dev/fuse` and `SYS_ADMIN`).

## Reliability and observability

- [ ] `TMC-OPS-1` Add a Docker healthcheck for `/health`.
- [ ] `TMC-OPS-2` Add log rotation for the TMC container.
- [ ] `TMC-OPS-3` Add integration tests for partial API failure, TMC restart and concurrent scan/refresh.
- [ ] `TMC-OPS-4` Add a fake TorBox API mode or fixture so CI does not hit the real API.
- [ ] `TMC-OPS-5` Monitor refresh duration, failure counts and `last_error`.
- [ ] `TMC-OPS-6` Decide whether to expose a `/metrics` endpoint.
- [ ] `TMC-OPS-7` Document upgrade order (TMC first, then plugin) and rollback.
- [x] `TMC-OPS-8` Keep `.env`, `config/`, `torbox/` and local compose files out of the image and Git.

## Documentation

- [ ] `TMC-DOC-1` Add a network diagram showing Jellyfin, TMC and the control API.
- [ ] `TMC-DOC-2` Document token generation and rotation.
- [ ] `TMC-DOC-3` Document the `CONTROL_MIN_INTERVAL` and plugin cooldown interaction.
- [ ] `TMC-DOC-4` Document the metadata-enabled slow-refresh case and how to raise the plugin timeout.
- [ ] `TMC-DOC-5` Document FUSE requirements (mount visibility and propagation).
- [ ] `TMC-DOC-6` Maintain the compatibility matrix with the plugin repo. Unblocks `PLG-DOC-4`.
- [ ] `TMC-DOC-7` Add TMC release and upgrade notes.

## Cross-repo dependency map

| TMC task | Plugin task it unblocks | Why |
|---|---|---|
| `TMC-API-1` | `PLG-H-13` | Plugin can check the control API version before calling it. |
| `TMC-API-2` | `PLG-H-5` | Plugin can poll a job instead of holding a long HTTP request. |
| `TMC-API-4` | `PLG-H-14` | Plugin client and docs use the documented response schema. |
| `TMC-REL-4` | `PLG-REL-3`, `PLG-DOC-4` | Plugin release notes and compatibility matrix reference a released TMC version. |
| `TMC-DOC-6` | `PLG-DOC-4` | One compatibility matrix for both repositories. |
| `TMC-DOC-1`, `TMC-DOC-3`, `TMC-DOC-4`, `TMC-DOC-5` | `PLG-DOC-1`, `PLG-DOC-3` | Plugin setup/troubleshooting links to TMC deployment docs. |
