# JavaScript TestServer

The TypeScript / browser implementation of the Couchbase Lite test server, built
on `@couchbase/lite-js`. Unlike the other platforms it talks to the test client
over **WebSocket** rather than HTTP (handled on the client side by
`client/src/cbltest/websocket_router.py`).

## Requirements

- Node.js + npm for working on the server directly.
- [`bun`](https://bun.sh) on `PATH` to run it through the orchestrator. Both CI and
  `start_local.py` shell out to `bun`, not `npm`.
- A desktop browser. The test server runs in a browser tab, so a run needs a desktop
  session. It never runs on a remote host, even when Sync Gateway is in AWS.
- Couchbase Lite is an npm dependency (`@couchbase/lite-js`).

## Build and Run

```
npm install
npm run dev
```

`npm run dev` starts the Vite dev server, which hosts the test server in the
browser. On connecting, the server exchanges an initial `Hello` WebSocket
message in place of the HTTP API-version / server-ID headers the other platforms
use.

## Tests and Linting

```
npm test             # Vitest (run once)
npm run test:browser # Vitest in a real browser (Playwright)
npm run test:watch   # Vitest in watch mode
npm run lint         # ESLint
npm run lint:fix     # ESLint with autofix
```

## Running the E2E Suites

Pick a backend for Sync Gateway. The test server itself is the same either way: the test
client hosts a WebSocket endpoint and opens `tdk.html` in your default browser.

### Against local Sync Gateway (rosmar)

Fastest loop, no AWS. Full detail in
[environment/local/README.md](../../environment/local/README.md).

```bash
uv run environment/local/start_local.py --server rosmar --git-tag main \
    --testserver-platform js --build-testserver 1.1.0-8
cd tests/dev_e2e
uv run pytest -v --config "$(cat ../../environment/local/topology_config)" test_basic_replication.py
```

### Against AWS (Couchbase Server + Sync Gateway on EC2)

First read [environment/aws/README.md](../../environment/aws/README.md) for AWS SSO, the
SSH config, and Terraform. Then run `aws sso login`.

**1. Trust the Sync Gateway CA (one time).** AWS Sync Gateway serves TLS with a certificate
from `Internal Test CA`. Every other platform pins that certificate, but a browser cannot,
so the replicator fails on an untrusted certificate until you trust the CA:

```bash
security add-trusted-cert -r trustRoot -k ~/Library/Keychains/login.keychain-db \
    environment/aws/sgw_setup/cert/ca_cert.pem
```

macOS prompts for your password. Remove it later with `security remove-trusted-cert` and
the same path.

> Weigh this first: `ca_key.pem` is committed next to the certificate, so that CA's private
> key is available to anyone with repo access. Once your machine trusts the root, anyone
> holding the key can issue a certificate for **any** hostname your browser will accept.

To avoid touching your trust store, point `$BROWSER` at a script that launches Chrome with
`--ignore-certificate-errors` and a throwaway `--user-data-dir`. The script must background
the browser and exit immediately, because `webbrowser.GenericBrowser` waits on the process
it starts and would otherwise block the run forever.

**2. Write a topology** to `environment/aws/topology_setup/topology.json`:

```json
{
    "$schema": "topology_schema.json",
    "defaults": { "cbs": { "version": "7.6.12" }, "sgw": { "version": "4.0.7" } },
    "tag": "js",
    "test_servers": [
        { "platform": "js", "cbl_version": "1.1.0-8", "location": "localhost", "download": false }
    ],
    "include": "default_topology.json"
}
```

`"location": "localhost"` is not a placeholder. Only Couchbase Server and Sync Gateway go to
EC2. Use `"download": true` only when the `prebuild-test-server` job has published a
`testserver.zip` for that build under
`latestbuilds/couchbase-lite-js/<version>/<build>/`. Otherwise keep `false`, which installs
the requested `@couchbase/lite-js` into this directory with `bun`.

**3. Start the backend:**

```bash
cd environment/aws
uv run python start_backend.py --topology topology_setup/topology.json \
    --tdk-config-in ../../jenkins/pipelines/dev_e2e/javascript/config.json \
    --tdk-config-out ../../tests/dev_e2e/config.json
```

If this fails with `Unable to connect to port 22`, the instances had not finished booting.
The orchestrator waits only 5 seconds after `terraform apply`. The instances still exist, so
re-run the same command with `--no-terraform-apply` to resume from where it stopped.

**4. Run the tests.** Your default browser opens a tab and keeps it open for the run:

```bash
cd tests/dev_e2e
uv run pytest -v --config config.json test_basic_replication.py
```

Expect roughly 8 minutes for those 12 tests against AWS, against under a minute on rosmar.
The browser reaches us-east-1 on every replication and every changes feed.

**5. Tear down.** This destroys the EC2 instances, then stops the local Vite server:

```bash
cd environment/aws
uv run python stop_backend.py --topology topology_setup/topology.json
```

CI runs the same path through
[jenkins/pipelines/dev_e2e/javascript/test.sh](../../jenkins/pipelines/dev_e2e/javascript/test.sh).

### Notes

- **CORS is already configured.** Sync Gateway must allow the `http://localhost:5173` origin,
  because the replicator runs inside the page. Both `environment/aws/sgw_setup/config/bootstrap.json`
  and the two `environment/local/sync_gateway_config/*.json` carry that block. A missing one
  shows up as `CBL-JS / 502 Server connection failed`.
- **Datasets come from GitHub**, not from your checkout. `tdkSchema.ts` points
  `kDatasetBaseURL` at `dataset/server/dbs/js/` on `main`, so local dataset edits do not apply.
- **`bun install` rewrites `package.json`** to the version you asked for. Revert it with
  `git checkout servers/javascript/package.json` if you do not intend to commit the bump.
- **Logs:** `server.log` in this directory holds Vite's output. The test server's own logs go
  to the browser JavaScript console.

See [servers/AGENTS.md](../AGENTS.md) for the shared architecture, the WebSocket
transport notes, and the full endpoint list.
