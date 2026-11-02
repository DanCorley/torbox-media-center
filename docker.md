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
  |                     |              |   GET /health, POST /refresh   |
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

`/health` returns `status`, `version`, `mode`, `last_finished`, `last_result`
and `last_error`. Use `last_error` and `last_result.duration_ms` for
monitoring. A refresh that fails leaves `last_error` set and the container
healthy (the API is still up); alert on that field, not only on container
health.

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
| Plugin (client) | cooldown in the plugin settings | Decides whether to call `/refresh` after a scan; usually 60-300s. |
| TMC (server) | `CONTROL_MIN_INTERVAL` (default `60`) | Rejects `/refresh` with `429` and a `retry_after` value if the previous refresh finished less than this many seconds ago. |

The effective minimum gap between refreshes is therefore the larger of the two,
and a plugin cooldown shorter than `CONTROL_MIN_INTERVAL` produces `429`s that
the plugin must handle. Recommended: leave the plugin cooldown at or above
`CONTROL_MIN_INTERVAL`, and set `CONTROL_MIN_INTERVAL` longer than a typical
refresh (for example 300 with metadata disabled).

`POST /refresh` with `{"force": true}` bypasses the interval check but not the
refresh lock: a concurrent refresh returns `409 refresh already running`.
`CONTROL_MIN_INTERVAL` does not affect the scheduled `MOUNT_REFRESH_TIME`
refresh; it only gates control-API requests.

## Metadata-enabled slow refresh and plugin timeout

With `ENABLE_METADATA=true`, TMC queries the TorBox metadata search endpoint
for each item and is subject to its rate limits (429s are expected). A refresh
can take minutes, which is much longer than a default plugin HTTP timeout.

- Prefer `ENABLE_METADATA=false` unless the player requires `movies/series`
  separation; `strm` output is much faster and does not hit the rate limit.
- If metadata is required, raise the plugin request timeout (for example to
  300-600 seconds) and set the proxy/read timeout at least as high.
- Set `CONTROL_MIN_INTERVAL` above the observed refresh duration so queued
  scan events do not immediately hit `429`.
- A refresh that exceeds the plugin timeout still completes on the TMC side.
  The plugin's retry then sees `429` while the lock is held (`409` if the
  refresh is still running). Treat both as "refresh in progress", not as a
  hard failure.

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

## Compatibility matrix

Keep this table in sync with the plugin repository (`PLG-DOC-4`). Fill a row
for every TMC release that changes the control API or the `.strm` layout.

| TMC version | Control API version | Jellyfin plugin | Jellyfin | Notes |
|---|---|---|---|---|
| 2.0.x | not reported yet | 0.1.x | 10.11.x | Baseline: bearer auth, `/health`, `/refresh`, `force`, `CONTROL_MIN_INTERVAL`. |
| _next_ | _1_ | _x.y.z_ | _10.11.x_ | _Update when `TMC-API-1` lands and `/health` reports the API version._ |

Rules:

- "Control API version" is the value reported by `/health` once
  `TMC-API-1` is implemented. Until then, use the TMC version.
- A plugin must be listed in a row before it is supported against that TMC
  version.
- Jellyfin 10.11.x is the tested baseline; older versions may work but are not
  supported for the scan-trigger flow.
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

1. Back up `.env` and note the current TMC image tag/digest.
2. Pull and start the new TMC image. Verify `GET /health` returns 200 and the
   fields you rely on are still present.
3. Trigger one manual refresh and confirm the `.strm` counts look normal.
4. Upgrade the Jellyfin plugin, restart Jellyfin if required, and save the
   plugin configuration.
5. Run a library scan and confirm the plugin receives 200 (or an expected
   429/409), not 401/404.

Rollback:

1. Pin the previous TMC tag/digest and recreate the container.
2. If the plugin was upgraded, roll it back to the version listed for that TMC
   version in the compatibility matrix.
3. Verify `/health`, then a manual refresh. TMC rebuilds its local JSON cache
   from the TorBox API on startup, so a rollback does not need a data restore;
   the `.strm` tree is the durable output.
4. If rollback is caused by a token/secret problem, restore the previous `.env`
   or secret file before restarting.
