# Load Balancer AWS setup

The contents of this folder all have to do with deploying and setting up one or more load balancers onto one or more AWS nodes so that at the end it is ready to go for E2E testing.  The steps that it takes are as follows:

1. Transfer configure-system.sh and Traefik config files to the remote node
2. Run configure-system.sh (see later section for details)
3. Sets up a local docker context that runs over SSH to the remote node
4. Starts a docker container of Traefik, or uses an existing one that it finds

## System Configuration

The AWS remote node is not going to have docker installed by default, so the configure-system.sh will do the following:

1. If docker is not found, install docker via yum and start its systemd service
2. If the user is not a member of the docker group, add the user to the docker group so that the user can run docker commands without sudo.

## Routing

Traefik listens on 4984 (public) and 4985 (admin), and fronts every Sync Gateway node
the topology lists as an upstream of that load balancer.

- A request with no `X-Backend` header goes to the round robin pool of all nodes. A node
  that is down refuses the connection, and Traefik then retries the request against the
  next node in the pool, as many times as there are nodes, so the pool keeps serving while
  nodes are down. A node that is gone rather than down black-holes the connection instead
  of refusing it, and the request waits out `dialTimeout` before moving on. An error
  answered by a node that is up, such as the 503 it returns while a database comes online,
  is not retried and reaches the client.
- A request with `X-Backend: sg-<index>` goes to that one node, where `<index>` is the
  node's position in the load balancer's upstream list. Use this to address a single node
  through the load balancer. Such a request is never served by another node, so it fails
  if that node is down: 502 when the node refuses the connection, 504 when it is gone.
- A request with an `X-Backend` value that names none of the upstreams, an empty value
  included, gets a 500, so a stale or mistyped index fails instead of quietly falling back
  to the round robin pool.
