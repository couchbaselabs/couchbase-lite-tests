# Couchbase Server AWS Setup

The contents of this folder all have to do with deploying and setting up Couchbase Server onto one or more AWS nodes so that at the end it is ready to go for E2E testing.  The steps that it takes are as follows:

1. Transfer configure-node.sh, configure-system.sh, and disable-thp.service to the remote node
2. Run configure-system.sh (see details in later section)
3. Download Couchbase Server RPM
4. Uninstall any installed Couchbase Server
5. Install Couchbase Server RPM
6. Start Couchbase systemd service
7. Run configure-node.sh (see details in later section)

## System Configuration

Before any logic is run, configure-system.sh is run to ensure that the system is ready to run Couchbase Server in an optimal way.  This involves three things:

1. Disable Transparent Huge Pages in the kernel as described in the [documentation](https://docs.couchbase.com/server/current/install/thp-disable.html).
2. Set kernel swappiness to 1 as described in the [documentation](https://docs.couchbase.com/server/current/install/install-swap-space.html)
3. Remove a sentinel file that is inserted after configure-node.sh is finished so that setup logic is not skipped.

## Node Configuration

After Couchbase Server is installed, it must be configured for use.  This will entail the following steps, accomplished with the help of the server CLI:

1. Wait for `http://localhost:8091/ui/index.html` to become available, signaling that the server is now running.
2. Depending on whether or not this node is going to be the first entry in a new cluster or not, do one of the following
   1. Initialize the cluster with the following:
      - Name: couchbase-lite-test
      - User: Administrator
      - Password: password
      - Cluster RAM: 8192 MiB
      - Index RAM: 2048 MiB
      - Services: data,query,index
   2. Add the node to the cluster, using a previous node as the cluster destination
3. Verify credentials were set up correctly by attempting to access the password protected URL `http://localhost:8091/settings/web`
4. Create an RBAC user for Sync Gateway to be able to log in with:
   - Username: admin
   - Password: password
   - Roles: `sync_gateway_dev_ops,sync_gateway_configurator[*],mobile_sync_gateway[*],bucket_full_access[*],bucket_admin[*]`