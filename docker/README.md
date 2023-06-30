When running `docker compose up`, there will be one Couchbase Server and one Sync Gateway started with the following endpoints:

### 1. travel

 | Config      | Value       |
 | ----------- | ----------- |
 | Database    | travel      |
 | Port        | 4984        |
 | Admin Port  | 4985        |
 | Collections | travel.airlines, travel.routes, travel.airports, travel.landmarks, travel.hotels |


### 2. names

 | Config      | Value             |
 | ----------- | ----------------- |
 | Database    | name              |
 | Port        | 4984              |
 | Admin Port  | 4985              |
 | Collections | _default._default |

### 3. posts

 | Config      | Value             |
 | ----------- | ----------------- |
 | Database    | name              |
 | Port        | 4984              |
 | Admin Port  | 4985              |
 | Collections | _default.posts    |


The Admin Credentials of Couchbase Server is `Administrator/password`.
The Admin Credentials of Sync Gateways is `admin/password` or `Administrator/password`.

### Docker Compose Environment Variables

The `docker-compose.yml` has 3 environment variables for configuration.

 | Variable      |   Description  |
 | ------------- | -------------- |
 | SG_DEB        | Sync Gateway 3.1+ deb file URL. Default is SG 3.1.0 Ubuntu ARM64 URL.                 |
 | SG_LEGACY_DEB | Sync Gateway 3.0 deb file URL. Default is SG 3.0.7 Ubuntu ARM64 URL.                  |
 | SSL           | Boolean flag to configure Sync Gateway for SSL endpoints. Default is false (FOR NOW). |

 Note: If you are using Mac x86-64, you must configure SG_DEB and SG_LEGACY_DEB to use x86_64 versions. 

 To configure environment variables, create `.env` file with the variables in key=value format.

 **Sample .env file for Mac x86-64**
```
SG_DEB=https://packages.couchbase.com/releases/couchbase-sync-gateway/3.1.0/couchbase-sync-gateway-enterprise_3.1.0_x86_64.deb
SG_LEGACY_DEB=https://packages.couchbase.com/releases/couchbase-sync-gateway/3.0.7/couchbase-sync-gateway-enterprise_3.0.7_x86_64.deb
```

### Some Commands

 |      Commands       |   Description  |
 | ------------------- | -------------- |
 | docker compose up   | Start all docker containers as specified in the `docker-compose.yml`. If the docker images and containers do not exists, they will be built first |
 | docker compose down | Stop running docker containers without deleting the containers |
 | docker compose down --rmi all | Stop running docker containers and deleting the images and containers |
