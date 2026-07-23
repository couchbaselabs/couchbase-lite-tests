# JavaScript TestServer

The TypeScript / browser implementation of the Couchbase Lite test server, built
on `@couchbase/lite-js`. Unlike the other platforms it talks to the test client
over **WebSocket** rather than HTTP (handled on the client side by
`client/src/cbltest/websocket_router.py`).

## Requirements

- Node.js + npm
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

See [servers/AGENTS.md](../AGENTS.md) for the shared architecture, the WebSocket
transport notes, and the full endpoint list.
