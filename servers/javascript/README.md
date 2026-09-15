# JavaScript TestServer

The TypeScript / browser implementation of the Couchbase Lite test server, built
on `@couchbase/lite-js`. Unlike the other platforms it talks to the test client
over **WebSocket** rather than HTTP (handled on the client side by
`client/src/cbltest/websocket_router.py`).

## Requirements

- [`bun`](https://bun.sh) on `PATH`. The orchestrator installs and starts the server with
  `bun`, so that is the supported path. `npm` works for hand runs.
- Node.js. `bun run dev` starts `vite` in a `node` child process.
- A desktop browser. The test server runs in a browser tab, so a run needs a desktop
  session. It never runs on a remote host.
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
own logs go to the browser JavaScript console.

## Tests and Linting

```
bun run test         # Vitest (run once)
bun run test:browser # Vitest in a real browser (Playwright)
bun run test:watch   # Vitest in watch mode
bun run lint         # ESLint
bun run lint:fix     # ESLint with autofix
```

See [servers/AGENTS.md](../AGENTS.md) for the shared architecture, the WebSocket
transport notes, and the full endpoint list.
