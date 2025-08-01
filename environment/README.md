*NOTE*: The docker backend is no longer supported.  It probably still functions but you use it with no warranty!  If it works for you that's great, but all future development is going into the much more scalable AWS backend.

## Commands

|      Commands       |   Description  |
| ------------------- | -------------- |
| docker compose up   | Start all docker containers as specified in the `docker-compose.yml`. If the docker images and containers do not exists, they will be built first |
| docker compose down | Stop running docker containers without deleting them |
| docker compose down --rmi all | Stop running docker containers, delete them and their images |

- The Admin Credentials for the Couchbase Server are `Administrator/password`.
- The Admin Credentials for the Sync Gateways UI are `Administrator/password`
- The Admin Credentials for the Sync Gateway REST API are `admin/password`

## Docker Compose Environment Variables

The `docker-compose.yml` has 3 environment variables for configuration.
These varaibles may be configured in a `.env` file with the variables in key=value format.

| Variable      |   Description  |
| ------------- | -------------- |
| SG_DEB_ARM64  | Sync Gateway 3.1+ deb file for ARM64 URL. Default is SG 3.1.0 Ubuntu ARM64 URL.       |
| SG_DEB_AMD64  | Sync Gateway 3.1+ deb file for x86-64 URL. Default is SG 3.1.0 Ubuntu x86-64 URL.     |
| SSL           | Boolean flag to configure Sync Gateway for SSL endpoints. Default is false (FOR NOW). |

 **Sample .env file *

```
SG_DEB_ARM64=https://packages.couchbase.com/releases/couchbase-sync-gateway/3.1.0/couchbase-sync-gateway-enterprise_3.1.0_aarch64.deb
SG_DEB_AMD64=https://packages.couchbase.com/releases/couchbase-sync-gateway/3.1.0/couchbase-sync-gateway-enterprise_3.1.0_x86_64.deb
SSL=false
```

## Running Tests

Note that many of the tests will require increasing Docker's default resource limits.  8G Memory and 80G disk seems to work.
