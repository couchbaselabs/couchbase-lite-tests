
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

## XDCR environemnt

This environment has two separate clusters of one Couchbase Server and one Sync Gateway node. There is an nginx load balancer that routes traffic to them.

To start the environment, run the following command:

```
docker-compose -f docker-compose-xdcr.yml up --build
```

To change the load balancer, edit the `nginx/nginx-2node.conf` file and run SIGHUP on the nginx process.

```
docker exec -it cbl-test-nginx kill -SIGHUP 1
```

After creating a bucket with server >= 7.6.4, run the following command on each bucket (once):

```
docker exec -it environment-cbl-test-cbs1 curl -u Administrator:password -X POST http://localhost:8091/pools/default/buckets/<bucket_name> -d enableCrossVectorVersioning=true
```

To set up XDCR, a remote cluster needs to be defined once on each cluster. Run:

```
docker exec -it environment-cbl-test-cbs1-1 curl -u Administrator:password -X POST http://localhost:8091/pools/default/remoteClusters -d name=cbs2 -d hostname=cbl-test-cbs2 -d username=Administrator -d password=password -d secure=full
docker exec -it environment-cbl-test-cbs1-1 curl -u Administrator:password -X POST http://localhost:8091/pools/default/remoteClusters -d name=cbs1 -d hostname=cbl-test-cbs1 -d username=Administrator -d password=password -d secure=full
```

To set up a mobile aware XDCR replication, the standard createReplication REST syntax can be used, with mobile=Active argument. This assumes there is a bucketA on cbs1 and bucketB on cbs2. The names of the buckets can be identical on both cluster.

```
docker exec -it environment-cbl-test-cbs1-1 curl -u Administrator:password -X POST http://localhost:8091/controller/createReplication -d name=cbs1-push -d toCluster=cbs2 -d fromBucket=bucketA -d toBucket=bucketB -d replicationType=continuous -mobile=Active
docker exec -it environment-cbl-test-cbs2-1 curl -u Administrator:password -X POST http://localhost:8091/controller/createReplication -d name=cbs2-push -d toCluster=cbs1 -d fromBucket=bucketB -d toBucket=bucketA -d replicationType=continuous -mobile=Active
```
