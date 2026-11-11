# Load Balancer AWS setup

This folder deploys one or more load balancers onto AWS nodes for E2E testing. For each node, `setup_load_balancers.py` does these steps:

1. Copy `configure-system.sh` to the node, and run it.
2. Remove a Traefik container that an older version of this setup left on a reused node.
3. Start a Caddy container (`caddy:2.10.2`) with no upstreams.

The topology file sets only how many load balancers to start (`"load_balancers": 1`). It does not choose upstreams.

## System Configuration

The AWS node does not have Docker by default, so `configure-system.sh` does these steps:

1. If Docker is not found, install Docker with dnf, and start its systemd service.
2. If the user is not a member of the docker group, add the user to the group. The user can then run docker commands without sudo.

## Ports

| Port | Use |
|------|-----|
| 4984 | Sync Gateway public API |
| 4985 | Sync Gateway admin API |
| 4990 | Caddy's admin API, which takes a new config at `/load` |

## Routing

A test sets the upstreams with `LoadBalancer.configure()` from `cbltest.api.loadbalancer`. Caddy applies the new config before it answers. `cluster_cleanup` removes every upstream before each test, so a test that needs a load balancer must configure it.

- A request with no `X-Backend` header goes round robin to every upstream. If an upstream refuses the connection, Caddy retries the request on the next upstream, once for each upstream. Caddy buffers each request body, up to 20 MB, so a retried POST keeps its body. If an upstream is gone, the connection hangs, and Caddy waits 5 seconds (`dial_timeout`) before it tries the next upstream. If an upstream that is up answers with an error, Caddy does not retry. An example is the 503 that Sync Gateway returns while a database comes online.
- A request with the header from `LoadBalancer.pin(sg)` goes to that one node, with no retry. If that node is down, the request fails with a 502.
- A request with any other `X-Backend` value, an empty one included, gets a 500. A stale or mistyped pin then fails, and does not fall back to round robin.
- With no upstreams, every request gets a 503.
