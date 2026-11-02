## Converting Commands to Docker Compose
Since Docker compose isn't as popular as Docker run commands, we only supplied the most common one [here](https://github.com/TorBox-App/torbox-media-center/blob/main/docker-compose.yaml), but since there are so many different iterations of the Docker run command, you can convert any Docker run command to a Docker compose file using [Composerize](https://www.composerize.com/), which is a pretty neat tool.

Simply paste in the Docker run command you need and it will accurately and instantly convert it to a Docker compose which you can then use in tools like [Portainer](https://www.portainer.io/), or create your own full compose file which includes Plex, Jellyfin, or Emby!

## Standard Docker Run Command (STRM)

Below is a standard Docker run command if spawning from the command line. Keep in mind the volume mount paths. If you change these in the environment variable, make sure you change it in the volume mount path.

```bash
docker run -it -d \
    --name=torbox-media-center \
    --restart=always \
    --init \
    -v /home/$(whoami)/torbox:/torbox \
    -e TORBOX_API_KEY=<EDIT_THIS_KEY> \
    -e MOUNT_METHOD=strm \
    -e MOUNT_PATH=/torbox \
    anonymoussystems/torbox-media-center:latest
```

## Standard Docker Run Command (FUSE)

Below is a standard Docker run command for using FUSE. Notice the difference when attaching the `/dev/fuse` device. We also needed to add the `--cap-add SYS_ADMIN` parameter. The Docker container needs access to the FUSE device of the system to activate the virtual file system.

> [!CAUTION]
> The `--cap-add SYS_ADMIN` parameter gives the container certain permissions which it would otherwise have. This is required to access the host systems FUSE device, but keep this in mind. You can read more about this [here](https://docs.docker.com/reference/cli/docker/container/run/#privileged).

```bash
docker run -it -d \
    --name=torbox-media-center \
    --restart=always \
    --init \
    --cap-add SYS_ADMIN \
    --device /dev/fuse \
    -v /mnt/torbox:/torbox:rshared \
    -e TORBOX_API_KEY=<EDIT_THIS_KEY> \
    -e MOUNT_METHOD=fuse \
    -e MOUNT_PATH=/torbox \
    anonymoussystems/torbox-media-center:latest
```


## Standard Docker Run Command Using GitHub Repository (STRM)

This config below is exactly the same as the above, except it is pulling from the GitHub repository rather than Docker Hub. Some people, find that GitHub is much faster than Docker, and sometimes Docker is down.
```bash
docker run -it -d \
    --name=torbox-media-center \
    --restart=always \
    --init \
    -v /home/$(whoami)/torbox:/torbox \
    -e TORBOX_API_KEY=<EDIT_THIS_KEY> \
    -e MOUNT_METHOD=strm \
    -e MOUNT_PATH=/torbox \
    ghcr.io/torbox-app/torbox-media-center:latest
```
## Docker Run Command Changing Location Of Files On Local System (STRM)

This config below changes where on the local system the files are mounted. Instead of in the home directory, it is now mounted in the `/mnt/torbox` directory, which is where you would be able to find your mounted files.

```bash
docker run -it -d \
    --name=torbox-media-center \
    --restart=always \
    --init \
    -v /mnt/torbox:/torbox \
    -e TORBOX_API_KEY=<EDIT_THIS_KEY> \
    -e MOUNT_METHOD=strm \
    -e MOUNT_PATH=/torbox \
    anonymoussystems/torbox-media-center:latest
```

## Docker Run Command Changing Location Of Files In Container (STRM)

This config below changes where on the Docker side where the files are stored. This isn't exactly necessary, but some people may want to change it, so here is a sample where the local system sees the mounted files at `/mnt/torbox` but inside the container, the files are now located at `/data`. Keep in mind that the `MOUNT_PATH` changed to reflect this.

```bash
docker run -it -d \
    --name=torbox-media-center \
    --restart=always \
    --init \
    -v /mnt/torbox:/data \
    -e TORBOX_API_KEY=<EDIT_THIS_KEY> \
    -e MOUNT_METHOD=strm \
    -e MOUNT_PATH=/data \
    anonymoussystems/torbox-media-center:latest
```

## Standard Docker Run Command Using The Very Latest Update (STRM)

Below is a standard Docker run command for running the bleeding edge of this repository. This usually isn't a good idea, but can be used for testing the latest updates, or debugging issues. For the latest release updates, use the `latest` Docker image tag. To get the latest nightly/bleeding edge/source updates straight from the repository, use the `main` Docker image tag. You also may use a commit SHA hash to get the image of a specific commit. For example: `sha-bdd4339`. This works with both GitHub and Docker repository URLs.

```bash
docker run -it -d \
    --name=torbox-media-center \
    --restart=always \
    --init \
    -v /home/$(whoami)/torbox:/torbox \
    -e TORBOX_API_KEY=<EDIT_THIS_KEY> \
    -e MOUNT_METHOD=strm \
    -e MOUNT_PATH=/torbox \
    anonymoussystems/torbox-media-center:main
```

---

# Control API: deployment, security and operations

These sections cover the Jellyfin refresh control API (`CONTROL_*` variables) and
the production concerns around it. The API is optional and disabled by default.

## Network layout (private network only)

The control API is an authenticated HTTP service. It must stay on a private
network and must never be published to the internet or to a host interface that
untrusted clients can reach.

```
                    private Docker network (compose default network)
  +---------------------+              +--------------------------------+
  | Jellyfin            |  HTTP +      | torbox-media-center            |
  | TorBox Refresh      |  Bearer      |   CONTROL_HOST=0.0.0.0          |
  | plugin              | -----------> |   CONTROL_PORT=8787 (expose)   |
  |                     |              |   GET /health                  |
  |                     |              |   POST /refresh (sync, v1)     |
  |                     |              |   POST /refresh/jobs (async)   |
  +----------+----------+              +----------------+---------------+
             |                                          |
             | reads .strm from the shared volume       | HTTPS + TORBOX_API_KEY
             v                                          v
  +---------------------+                      +----------------------+
  | shared /torbox      |                      | api.torbox.app       |
  | volume on the host  |                      | (public internet)    |
  +---------------------+                      +----------------------+
```

Rules:

- Use `expose: ["8787"]` (compose) or nothing at all. `expose` only documents
  the port inside the network; it does not publish it on the host.
- Do **not** add `ports: ["8787:8787"]`. If a reverse proxy runs on the same
  host, bind to loopback only: `ports: ["127.0.0.1:8787:8787"]`.
- Do **not** mark the network `internal: true`: TMC still needs outbound HTTPS
  to the TorBox API and to the metadata search endpoint.
- Run Jellyfin and TMC in the same compose project so the plugin can call
  `http://torbox-media-center:8787` by service name.

## Control API contract (v2)

`CONTROL_API_VERSION` is `2` and `GET /health` reports it as `api_version`.
Every endpoint requires `Authorization: Bearer <CONTROL_TOKEN>`; a missing or
wrong token returns `401`. The server only starts when `CONTROL_ENABLED=true`
and `CONTROL_TOKEN` is non-empty.

| Method and path | Behavior | Success |
|---|---|---|
| `GET /health` | Liveness plus `api_version`, TMC `version`, `mode`, `last_finished`, `last_result`, `last_error`. | `200` |
| `POST /refresh` | Synchronous refresh. Returns the refresh result. Retained for plugin **1.0.0** compatibility. | `200` |
| `POST /refresh/jobs` | Queues one async refresh job and returns a job handle. | `202` |
| `GET /refresh/jobs/{id}` | Returns job status, timestamps, result or error. | `200` |

Health response:

```json
{
  "status": "ok",
  "api_version": 2,
  "version": "<TMC version>",
  "mode": "strm",
  "last_finished": 1762070400.0,
  "last_result": null,
  "last_error": null
}
```

Async job creation:

```json
{
  "job_id": "<32 hex characters>",
  "status": "queued",
  "status_url": "/refresh/jobs/<job_id>"
}
```

Job status:

```json
{
  "job_id": "<id>",
  "status": "completed",
  "started_at": 1762070400.0,
  "finished_at": 1762070430.0,
  "result": { "added": 3, "removed": 0, "updated": 1, "changed": 4, "partial": false, "mode": "strm", "duration_ms": 30000 },
  "error": null
}
```

- `status` is `queued`, `running`, `completed` or `failed`. A failed job sets
  `error` and leaves `result` null.
- Timestamps (`last_finished`, `started_at`, `finished_at`) are Unix epoch
  seconds.
- The refresh result contains `refreshed`, `added`, `removed`, `updated`,
  `changed`, `partial`, `errors`, `mode` and `duration_ms`.
- Only one refresh runs at a time (scheduled, sync or async). A concurrent
  async request gets `409` with `job_id`/`active_job_id`; the synchronous
  endpoint gets `409` when the lock is held, or `429` if the cooldown check
  runs first.
- `{"force": true}` skips the `CONTROL_MIN_INTERVAL` cooldown but not the
  refresh lock.
- The server retains the **last 20 finished jobs**. Older jobs are evicted and
  `GET /refresh/jobs/{id}` returns `404`.

Idempotency: send an `Idempotency-Key` header with `POST /refresh/jobs`. A
repeated key returns `202` for the same job (with its current status) instead of
starting a new refresh, including after the job completed. The mapping is
removed when the job falls out of the 20-job window. The synchronous endpoint
has no idempotency support.

Status codes:

| Code | Meaning |
|---|---|
| `200` | Health, synchronous refresh result, or job read. |
| `202` | Async job accepted or idempotently replayed. |
| `400` | Request body is not valid JSON. |
| `401` | Missing or incorrect bearer token. |
| `404` | Unknown path or unknown/evicted job ID. |
| `409` | A refresh is already running. |
| `429` | Cooldown active. Body: `{"error":"cooldown","retry_after":<seconds>}` plus `Retry-After`. |
| `500` | Synchronous refresh failed. Async failures appear as `status: failed` on the job. |

Compatibility: plugin 1.0.0 calls synchronous `POST /refresh`. Plugin 1.1.0
probes `GET /health`, uses `POST /refresh/jobs` when `api_version >= 2`, and
falls back to the synchronous endpoint when `/health` returns `404` or an
unreadable payload. A `401` is never treated as a fallback.

## Generating and rotating the control token

Generate a dedicated random token; never type a password or reuse another
credential:

```bash
# 32 random bytes, hex encoded
openssl rand -hex 32

# or, without OpenSSL
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

Put it in `.env` (or the secret file described below) and restart TMC:

```dotenv
CONTROL_ENABLED=true
CONTROL_HOST=0.0.0.0
CONTROL_PORT=8787
CONTROL_TOKEN=<generated-token>
CONTROL_MIN_INTERVAL=60
```

Set the same token in the Jellyfin plugin (Dashboard -> Plugins -> TorBox
Refresh -> Token). A `401 unauthorized` from `/health` or `/refresh` means the
two values differ.

Rotation:

1. Generate a new token.
2. Update `CONTROL_TOKEN` for TMC and restart the container. The token is read
   once at process start, so a restart is required.
3. Update the plugin configuration with the new token and save.
4. Verify: `GET /health` returns 200 and a manual refresh succeeds.

TMC accepts exactly one token at a time, so expect a short window where the
plugin is rejected. Rotate during a maintenance window, or rotate the plugin
first and accept rejected refreshes until TMC restarts. Every rejected request
returns `401` and is safe to retry.

The plugin stores the token in Jellyfin's plugin configuration XML inside the
Jellyfin config directory, in plain text. Restrict that directory to the
Jellyfin user, exclude it from shared backups, and treat it as a secret. TMC
keeps its copy in the environment or the Docker secret file; rotating one side
without the other produces `401` until both match.

## Do not reuse the TorBox API key

`CONTROL_TOKEN` and `TORBOX_API_KEY` are different credentials:

- `TORBOX_API_KEY` grants full access to your TorBox account (downloads,
  account, billing-adjacent endpoints).
- `CONTROL_TOKEN` only authorizes local refresh calls.

If the control token leaks, an attacker can trigger refreshes. If the TorBox
API key leaks, the account is compromised. Use a separate random value for each
and rotate them independently. Also do not reuse the token between TMC
instances or environments.

## Secrets: env files and Docker secrets

`.env` is git-ignored and excluded from the image by `.dockerignore`. On the
host, restrict it:

```bash
chmod 600 .env
chown "$(id -u):$(id -g)" .env
```

Do not bake secrets into images, `Dockerfile`, `docker-compose.yaml`, CI logs or
committed compose overrides.

For Docker secrets, the app reads environment variables, so export the secret
in the container entrypoint. Compose escapes `$$` to a literal `$`:

```yaml
services:
  torbox-media-center:
    secrets:
      - control_token
      - torbox_api_key
    entrypoint:
      - /bin/sh
      - -c
      - >-
        export CONTROL_TOKEN=$$(cat /run/secrets/control_token);
        export TORBOX_API_KEY=$$(cat /run/secrets/torbox_api_key);
        exec python main.py
secrets:
  control_token:
    file: ./secrets/control_token.txt
  torbox_api_key:
    file: ./secrets/torbox_api_key.txt
```

Keep `./secrets/` out of Git (it is in `.dockerignore`) and `chmod 600` the
files. Docker Swarm secrets work the same way when the stack is deployed with
`docker stack deploy`. Avoid passing secrets with `docker run -e` on shared
machines: they are visible in `docker inspect` and shell history.

## TLS and reverse proxy for cross-host deployments

TMC serves plain HTTP. The bearer token is sent in clear text, so any traffic
that leaves the Docker host must be encrypted. Prefer one of:

- Both containers on the same private Docker network (no TLS needed).
- WireGuard, Tailscale or another encrypted private network.
- A TLS-terminating reverse proxy in front of TMC.

Reverse proxy example (nginx, proxy on the same host, TMC bound to
`127.0.0.1:8787`):

```nginx
server {
    listen 443 ssl;
    server_name tmc.internal.example;

    ssl_certificate     /etc/ssl/certs/tmc.crt;
    ssl_certificate_key /etc/ssl/private/tmc.key;

    location / {
        proxy_pass http://127.0.0.1:8787;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        # Forward the plugin's bearer token unchanged.
        proxy_set_header Authorization $http_authorization;
        proxy_set_header X-Request-ID $request_id;
        # Refreshes can be slow with metadata enabled.
        proxy_read_timeout 300s;
    }
}
```

Then configure the plugin URL as `https://tmc.internal.example` and make sure
Jellyfin trusts the proxy CA. If the proxy strips `Authorization`, every call
returns `401`. Do not put TMC behind a public hostname without TLS, and do not
use a proxy that caches `POST /refresh`.

## Healthcheck, logs and monitoring

The image and the compose file define a healthcheck for `GET /health` using
only the Python standard library:

- The probe exits `0` when `CONTROL_ENABLED` is not `true` (API disabled).
- When enabled, it sends `Authorization: Bearer $CONTROL_TOKEN` to
  `http://127.0.0.1:$CONTROL_PORT/health`.
- It exits non-zero on connection failure or `401`.

Check it with:

```bash
docker inspect --format '{{.State.Health.Status}}' torbox-media-center
docker inspect --format '{{json .State.Health.Log}}' torbox-media-center | jq
```

Manual probe (never paste the token into shared logs):

```bash
curl -fsS -H "Authorization: Bearer $CONTROL_TOKEN" \
  http://127.0.0.1:8787/health
```

`/health` returns `status`, `api_version` (`2`), `version`, `mode`,
`last_finished`, `last_result` and `last_error`. Use `last_error` and
`last_result.duration_ms` for monitoring. A refresh that fails leaves
`last_error` set and the container healthy (the API is still up); alert on that
field, not only on container health. To watch an in-flight async refresh, poll
`GET /refresh/jobs/{id}` and alert when `status` stays `running` beyond the
expected duration or becomes `failed`.

The health payload is also the plugin's API-version probe: the plugin only uses
async jobs when `api_version >= 2`. Keep `GET /health` reachable and free of
proxy caching, and do not change its schema without bumping
`CONTROL_API_VERSION`.

Log rotation is configured for the TMC service in `docker-compose.yaml`
(`json-file`, `max-size: 10mb`, `max-file: 5`). Tune these for your retention
policy; without them Docker grows the JSON log until the disk fills.

Structured refresh logs should record, at minimum: timestamp, level, event
name, request ID, duration in milliseconds, added/removed/updated/unchanged
counts, partial-failure count and error type. They must never contain
`CONTROL_TOKEN`, `TORBOX_API_KEY`, the `Authorization` header or `.strm` URLs.
The logging implementation is owned by the API code, not by these deployment
files; this section is the required field contract.

Metrics: no `/metrics` endpoint is exposed in this release. Scrape `/health`
plus container logs, or put a blackbox exporter in front of `/health` with the
bearer token. Revisit `TMC-OPS-6` if Prometheus is already deployed.

## Refresh timing: CONTROL_MIN_INTERVAL and the plugin cooldown

There are two independent throttles:

| Layer | Setting | Behavior |
|---|---|---|
| Plugin (client) | cooldown in the plugin settings (default `300`) | Decides whether to call TMC after a scan; skips the call entirely while cooling down. |
| TMC (server) | `CONTROL_MIN_INTERVAL` (default `60`) | Rejects `POST /refresh` or `POST /refresh/jobs` with `429`, a `retry_after` value and a `Retry-After` header if the previous refresh finished less than this many seconds ago. |

The effective minimum gap between refreshes is therefore the larger of the two,
and a plugin cooldown shorter than `CONTROL_MIN_INTERVAL` produces `429`s that
the plugin treats as a no-op. Recommended: leave the plugin cooldown at or above
`CONTROL_MIN_INTERVAL`, and set `CONTROL_MIN_INTERVAL` longer than a typical
refresh (for example 300 with metadata disabled).

`{"force": true}` bypasses the interval check but not the refresh lock: a
concurrent request returns `409` with the active `job_id` (async) or
`{"error":"refresh already running"}` (sync). Repeated scan triggers can also
send an `Idempotency-Key` to `POST /refresh/jobs`; a replay returns `202` for the
existing job instead of a second `409`. `CONTROL_MIN_INTERVAL` does not affect
the scheduled `MOUNT_REFRESH_TIME` refresh; it only gates control-API requests.

## Metadata-enabled slow refresh and plugin timeout

With `ENABLE_METADATA=true`, TMC queries the TorBox metadata search endpoint
for each item and is subject to its rate limits (429s are expected). A refresh
can take minutes, which is much longer than a default plugin HTTP timeout.

- Prefer `ENABLE_METADATA=false` unless the player requires `movies/series`
  separation; `strm` output is much faster and does not hit the rate limit.
- If metadata is required, raise the plugin **Request timeout** (for example to
  300-600 seconds) and set the proxy/read timeout at least as high. With async
  jobs this value is the overall polling deadline; the plugin polls every 2
  seconds until `completed` or `failed`.
- Set `CONTROL_MIN_INTERVAL` above the observed refresh duration so queued
  scan events do not immediately hit `429`.
- A refresh that exceeds the plugin timeout still completes on the TMC side.
  The plugin's retry then sees `429` while the lock is held (`409` if the
  refresh is still running). Treat both as "refresh in progress", not as a
  hard failure. The job remains readable at `GET /refresh/jobs/{id}` until it
  falls out of the 20-job retention window.

## FUSE mount visibility and propagation

`strm` is recommended for Jellyfin and needs no special mount flags. For
`fuse`:

- Pass the FUSE device: `--device /dev/fuse` and `cap_add: [SYS_ADMIN]`
  (compose: `devices: ["/dev/fuse:/dev/fuse"]`).
- Use shared or rshared propagation so the mount created inside the TMC
  container is visible to Jellyfin on the host and in the Jellyfin container:
  - host: `mount --make-rshared /mnt/torbox`
  - TMC: `-v /mnt/torbox:/torbox:rshared`
  - Jellyfin: mount the same host path, also with `rshared`
- In compose syntax:

  ```yaml
  volumes:
    - type: bind
      source: /mnt/torbox
      target: /torbox
      bind:
        propagation: rshared
  ```

- If propagation is missing, Jellyfin may see an empty directory or stale
  entries after TMC remounts. The mount must also survive container restarts;
  do not let Jellyfin start before TMC has mounted if it caches the directory.
- Do not run more than one TMC instance against the same host FUSE mount path.

## Non-root STRM mode

`strm` only needs write access to the output directory, so it can run as a
non-root user:

```yaml
services:
  torbox-media-center:
    user: "1000:1000"
```

Then make the host directory writable by that UID/GID:

```bash
sudo chown -R 1000:1000 /path/to/torbox
```

The image does not implement `PUID`/`PGID` (those are Jellyfin/LinuxServer
variables); use `user:` instead. `CONTROL_PORT=8787` is unprivileged, so no
capability is needed. `strm` mode does not require `SYS_ADMIN`.

`fuse` mode still needs `/dev/fuse` and `SYS_ADMIN`, and normally runs as root
inside the container. Non-root FUSE setups depend on a setuid `fusermount` and
host configuration; treat them as unsupported unless you have verified them.

## TorBox API-key exposure in .strm files (accepted design constraint)

Each `.strm` file contains a TorBox download URL. Those links embed your TorBox
account credential, so anyone who can read the library can extract the API key
and use it outside TMC.

This is a known and accepted constraint of the `strm` mount method, not a bug:

- Restrict the library to the media-server user:
  `chmod -R o-rwx /path/to/torbox` and keep the parent directory `750`.
- Never expose the library over SMB/NFS/HTTP to untrusted users, and do not
  commit or share `.strm` files.
- Do not back the library up to cloud storage unencrypted.
- If a key leaks, revoke it in TorBox settings and update `TORBOX_API_KEY`.
  Rotating the control token does not help here; they are separate credentials.
- `fuse` mode does not write API keys to disk files, at the cost of the FUSE
  requirements above.

## Troubleshooting the control API and plugin

### `401 unauthorized`

- The plugin token and `CONTROL_TOKEN` differ. Re-enter the exact value in
  **Dashboard -> Plugins -> TorBox Refresh** and in `.env`/the secret file.
- TMC reads `CONTROL_TOKEN` once at process start. Restart the container after
  changing it; editing `.env` alone does nothing.
- A reverse proxy or ingress stripped the `Authorization` header. Configure it
  to pass the header through unchanged.
- The request used `TORBOX_API_KEY` by mistake. The control token is a separate
  credential.
- After rotation, expect `401` until both sides carry the new value. It is safe
  to retry.

### `409 refresh already running`

A scheduled `MOUNT_REFRESH_TIME` refresh, a manual request, or an earlier scan
still holds the single refresh lock. `force: true` does not bypass it. Async
`409` responses include `job_id` and `active_job_id`; poll
`GET /refresh/jobs/{id}` instead of retrying. The plugin treats `409` as
"already handled" and does not queue a follow-up scan.

### `429 cooldown`

`CONTROL_MIN_INTERVAL` has not elapsed since the last refresh finished. The
response contains `retry_after` and a `Retry-After` header. This is not an
error in the plugin: it is a no-op, and the plugin does not queue a second
scan. If `429`s are frequent, raise the plugin cooldown to at least
`CONTROL_MIN_INTERVAL`, or raise `CONTROL_MIN_INTERVAL` above the refresh
duration. `force: true` skips this check; the plugin does not send it.

### Side-loaded plugin and repository warnings

Jellyfin warns when a plugin is side-loaded, when a repository is not trusted,
or when two plugins share a GUID. To avoid this:

1. Remove any manually copied folder under `<jellyfin config>/plugins/TorBoxRefresh`.
2. Add the manifest URL under **Dashboard -> Plugins -> Repositories** and
   install **TorBox Refresh** from the catalog.
3. Restart Jellyfin after adding or removing plugin files.
4. Keep the plugin GUID `a7c2f0e4-6b1d-4f3a-9c8e-2d5b7a1e4f60` stable; a
   manifest entry with a different GUID creates a duplicate.

The catalog entry currently has no custom icon, so Jellyfin may show a
placeholder image. That is expected and does not affect refreshes.

### Two-scan sequence

`ILibraryPostScanTask` runs after Jellyfin has already walked the library, so
the files added by a refresh cannot be seen by the same scan. The expected flow
is:

1. First scan finishes walking the old mount.
2. Post-scan task calls TMC and gets change counts.
3. If `changed > 0` and `QueueFollowUpScan` is enabled, Jellyfin queues one
   follow-up scan.
4. Second scan walks the updated mount and picks up the new files.
5. The second scan's post-scan task hits the plugin cooldown and stops, so no
   scan loop occurs.

An unchanged mount, a failed refresh, and a `409`/`429` all produce
`changed = 0` and therefore no follow-up scan. Do not disable the follow-up
scan unless another tool watches the mount.

### Token storage

TMC reads the token from `CONTROL_TOKEN` in the environment or the exported
Docker secret. The plugin stores the same value in Jellyfin's plugin
configuration XML (plain text) in the Jellyfin config directory. Protect that
directory with filesystem permissions, keep it out of shared backups, and
rotate the control token if it leaks. Rotating the TorBox API key does not
rotate the control token, and vice versa.

### Cooldown and timeouts

- The effective gap between refreshes is
  `max(plugin cooldown, CONTROL_MIN_INTERVAL)`. The plugin's default cooldown is
  300 seconds; TMC's default is 60 seconds.
- The plugin's **Request timeout** is a per-request timeout for the synchronous
  endpoint and the overall deadline for async job polling. The plugin polls
  every 2 seconds.
- TMC keeps working after the plugin times out. A later retry sees `409` while
  the lock is held or `429` during the cooldown; both mean "in progress", not
  "failed".
- For cross-host reverse proxies, set the read timeout at least as high as the
  expected refresh duration.

### Metadata-enabled slow refreshes

With `ENABLE_METADATA=true`, TMC calls the TorBox metadata search endpoint per
item and can take minutes; `429`s from TorBox are expected. This is usually much
longer than a default plugin timeout. Either keep metadata disabled (fast,
no rate limit) or raise the plugin timeout to 300-600 seconds and raise
`CONTROL_MIN_INTERVAL` above the observed duration. A refresh that outlives the
plugin timeout still finishes on TMC and can be inspected via
`GET /refresh/jobs/{id}`. See
[Metadata-enabled slow refresh and plugin timeout](#metadata-enabled-slow-refresh-and-plugin-timeout).

## Compatibility matrix

Keep this table in sync with the plugin repository (`PLG-DOC-4`). Fill a row
for every TMC release that changes the control API or the `.strm` layout.

| TMC version | Control API version | Jellyfin plugin | Jellyfin | Notes |
|---|---|---|---|---|
| 2.0.x | not reported | 0.1.x | 10.11.x | Legacy baseline: bearer auth, `/health`, synchronous `/refresh`, `force`, `CONTROL_MIN_INTERVAL`. |
| next 2.x (`feat/jellyfin-refresh-control-api`) | **2** | **1.1.0** | **12.4.0** | `/health` reports `api_version: 2`; async `POST /refresh/jobs` + polling, `Idempotency-Key`, 20-job retention. Synchronous `/refresh` stays for plugin 1.0.0. |
| _pending_ | _2_ | _1.1.x_ | _13.x_ | **Not available.** Jellyfin 13.x `Jellyfin.Controller` / `Jellyfin.Model` NuGet packages are unpublished, so there is no 13.x plugin artifact yet. |

Rules:

- "Control API version" is the `api_version` value reported by `GET /health`.
  A server that does not report it is treated as legacy by plugin 1.1.0.
- Plugin 1.1.0 requires control API v2 for async jobs. It still works against a
  legacy TMC by falling back to synchronous `POST /refresh` when `/health`
  returns `404` or an unreadable payload.
- A plugin must be listed in a row before it is supported against that TMC
  version.
- Jellyfin **12.4.0** (`targetAbi` `12.4.0.0`) is the tested baseline. Jellyfin
  13.x is pending until the NuGet packages are published; do not claim 13.x
  support.
- Pin both the TMC image tag and the plugin version in production.

## Release, upgrade and rollback

Release notes for TMC:

- Images are published to `ghcr.io/<owner>/<repo>` by
  `.github/workflows/docker-build.yml`. Tags follow semver (`vX.Y.Z`), plus
  `latest` and `main`/branch tags for testing. `main` is not a production tag.
- Pin production to a released tag or image digest, not `latest`.
- A release that changes the control API must update the compatibility matrix
  above and the plugin repository.

Upgrade order (the API is additive, so TMC first):

1. Back up `.env` and the Jellyfin plugin config XML; note the current TMC
   image tag/digest and plugin version.
2. Pull and start the new TMC image. Verify `GET /health` returns 200 with
   `api_version: 2` and the other fields you rely on.
3. Trigger one manual refresh. On v2 expect `POST /refresh/jobs` to return 202
   and the job to reach `completed`; `POST /refresh` still returns 200.
   Confirm the `.strm` counts look normal.
4. Upgrade the Jellyfin plugin (1.1.0 for async jobs), restart Jellyfin if
   required, and save the plugin configuration.
5. Run a library scan and confirm the plugin receives `202` and polls to
   `completed`, or an expected `409`/`429` no-op, not `401`/`404`.

Rollback:

1. Pin the previous TMC tag/digest and recreate the container.
2. If the plugin was upgraded, roll it back to the version listed for that TMC
   version in the compatibility matrix.
3. Verify `/health`, then a manual refresh. TMC rebuilds its local JSON cache
   from the TorBox API on startup, so a rollback does not need a data restore;
   the `.strm` tree is the durable output.
4. If rollback is caused by a token/secret problem, restore the previous `.env`
   or secret file before restarting.
