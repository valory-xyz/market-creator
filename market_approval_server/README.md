# Market approval server

A small Flask server that holds the markets proposed by the market-creator agent
until they are approved and processed. The agent talks to it over HTTP with an
API key. The endpoints are listed in the docstring of
[market_approval_server.py](market_approval_server.py) and on the server's main page.

## State file

The server keeps its whole state in one JSON file. `MARKET_APPROVAL_SERVER_CONFIG_FILE`
gives its path; the default is `server_config.json` in the working directory.

The file must exist before the server starts, or the server exits. A new
deployment starts from this content, with the SHA-256 hash of each API key
as a key under `api_keys`:

```json
{
    "proposed_markets": {},
    "approved_markets": {},
    "rejected_markets": {},
    "processed_markets": {},
    "api_keys": {"<sha256 of the API key>": "<user name>"}
}
```

```bash
echo -n "your_api_key" | sha256sum
```

The server rewrites this file on every request that changes a market. It writes
a temporary file next to it (`<file>.tmp`) and renames it, so the directory must
be writable. Do not put the state file inside the image.

## Run locally

```bash
cd market_approval_server
pip install -r requirements.txt
MARKET_APPROVAL_SERVER_CONFIG_FILE=/path/to/server_config.json \
  python3 -m flask --app market_approval_server.py run --host=0.0.0.0
```

Tests: `python -m pytest market_approval_server/tests` from the repository root.

## Docker image

The image is `valory/market_approval_server:<version>`, built from the
[Dockerfile](Dockerfile) in this folder. It contains the server and its template.

```bash
docker build -t valory/market_approval_server:local market_approval_server
docker run -p 5000:5000 -v /path/to/state:/data \
  -e MARKET_APPROVAL_SERVER_CONFIG_FILE=/data/server_config.json \
  valory/market_approval_server:local
```

## Deployment

What a deployment has to provide:

- One container per state file. Requests are serialized by a lock inside the
  process, so two containers, or two replicas, sharing a file would overwrite
  each other.
- A persistent volume, mounted at a directory, with `MARKET_APPROVAL_SERVER_CONFIG_FILE`
  pointing at a file in it. The container runs as root and needs to write there.
- Port 5000, plain HTTP. The API key travels in the `Authorization` header, so
  terminate TLS in front of the container.
- A readiness probe on `GET /`. That page is served without the lock, so it
  answers while a save is in progress. Every other endpoint waits for the lock.
- Memory for the state held in memory plus a serialized copy of it during a
  save or a large `GET`. Size the limit from the state file, and back up the
  volume.

To deploy a new version, set the new image tag and roll the pod. The server
reads the existing state file at startup, and removes the proposed markets whose
resolution time has passed. The format of the state file has not changed, so a
rollback is the previous tag.

## Release

The image is released together with the agent. Publishing a GitHub release
`vX.Y.Z` runs [release.yml](../.github/workflows/release.yml), which pushes
`valory/market_approval_server:X.Y.Z` next to `valory/oar-market_maker:X.Y.Z`.
The tag has no `v` prefix, there is one image for every deployment, and
`latest` is not pushed. A release does not change a running server.
