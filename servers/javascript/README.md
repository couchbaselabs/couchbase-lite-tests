# JavaScript TestServer

The TypeScript / browser implementation of the Couchbase Lite test server, built
on `@couchbase/lite-js`. Unlike the other platforms it talks to the test client
over **WebSocket** rather than HTTP (handled on the client side by
`client/src/cbltest/websocket_router.py`).

## Requirements

- [`bun`](https://bun.sh) on `PATH`. The orchestrator installs and starts the server with
  `bun`, so that is the supported path. `npm` works for hand runs.
- Node.js. `bun run dev` starts `vite` in a `node` child process.
- Playwright's Chromium. The test server runs in a browser tab, which the Python client
  opens in headless Chromium. Install it once with `uv run playwright install chromium`.
- Couchbase Lite is an npm dependency (`@couchbase/lite-js`).

## Build and Run

```
bun install
bun run dev
```

`bun run dev` starts the Vite dev server, which hosts the test server in the
browser. On connecting, the server exchanges an initial `Hello` WebSocket
message in place of the HTTP API-version / server-ID headers the other platforms
use. Vite writes its output to `server.log` in this directory; the test server's
own logs go to the browser JavaScript console, which the Python client writes to
`browser_log/<device>.log` in the pytest working directory.

## Reserved `ts_` Prefix

WebSocket messages have no headers, so each request and response carries its
metadata (`ts_id`, `ts_command`, `ts_serverID`, `ts_apiVersion`, `ts_error`, ...)
as top-level `ts_*` fields alongside the payload. A response such as
`/getDocument` spreads the document body into that same object, and the Python
client strips every `ts_*` key before handing the body on. Test documents must
therefore never use top-level properties starting with `ts_`: they would be
dropped, and `ts_id` or `ts_error` would also break request matching or error
detection.

## Tests and Linting

```
bun run test         # Vitest (run once)
bun run test:browser # Vitest in a real browser (Playwright)
bun run test:watch   # Vitest in watch mode
bun run format       # Biome formatter
bun run lint         # ESLint
bun run lint:fix     # ESLint with autofix
```

See [servers/AGENTS.md](../AGENTS.md) for the shared architecture, the WebSocket
transport notes, and the full endpoint list.
