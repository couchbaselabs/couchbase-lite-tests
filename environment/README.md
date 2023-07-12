
## Commands

|      Commands       |   Description  |
| ------------------- | -------------- |
| docker compose up   | Start all docker containers as specified in the `docker-compose.yml`. If the docker images and containers do not exists, they will be built first |
| docker compose down | Stop running docker containers without deleting them |
| docker compose down --rmi all | Stop running docker containers, delete them and their images |


## Service Endpoints

Running `docker compose up` will start one Couchbase Server and one Sync Gateway.
The Sync Gateway will have the following endpoints:

### 1. travel

| Config      | Value       |
| ----------- | ----------- |
| Database    | travel      |
| Port        | 4984        |
| Admin Port  | 4985        |
| Collections | travel.airlines, travel.routes, travel.airports, travel.landmarks, travel.hotels |
| Users | user1,pass |

### 2. names

| Config      | Value             |
| ----------- | ----------------- |
| Database    | name              |
| Port        | 4984              |
| Admin Port  | 4985              |
| Collections | _default._default |
| Users | user1,pass |

### 3. posts

| Config      | Value             |
| ----------- | ----------------- |
| Database    | name              |
| Port        | 4984              |
| Admin Port  | 4985              |
| Collections | _default.posts    |
| Users | user1,pass |

- The Admin Credentials for the Couchbase Server are `Administrator/password`.
- The Admin Credentials for the Sync Gateways UI are `Administrator/password`
- The Admin Credentials for the Sync Gateway REST API are `admin/password`


## Docker Compose Environment Variables

The `docker-compose.yml` has 3 environment variables for configuration.
These varaibles may be configured in a `.env` file with the variables in key=value format.

| Variable      |   Description  |
| ------------- | -------------- |
| SG_DEB        | Sync Gateway 3.1+ deb file URL. Default is SG 3.1.0 Ubuntu ARM64 URL.                 |
| SG\_LEGACY_DEB | Sync Gateway 3.0 deb file URL. Default is SG 3.0.7 Ubuntu ARM64 URL.                 |
| SSL           | Boolean flag to configure Sync Gateway for SSL endpoints. Default is false (FOR NOW). |

 **Sample .env file for Mac x86-64**

```
SG_DEB=https://packages.couchbase.com/releases/couchbase-sync-gateway/3.1.0/couchbase-sync-gateway-enterprise_3.1.0_x86_64.deb
SG_LEGACY_DEB=https://packages.couchbase.com/releases/couchbase-sync-gateway/3.0.7/couchbase-sync-gateway-enterprise_3.0.7_x86_64.deb
```
