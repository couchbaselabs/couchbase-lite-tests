# Sync Gateway AWS setup

The contents of this folder all have to do with deploying and setting up Sync Gateway onto one or more AWS nodes so that at the end it is ready to go for E2E testing.  The steps that it takes are as follows:

1. (if prerelease build) Download Sync Gateway RPM from latestbuilds
2. Transfer configure-system.sh to remote node
3. Run configure-system.sh (see later section for details)
4. Depending on if the desired Sync Gateway version is prerelease or not
   - (prerelease) Transfer Sync Gateway RPM to remote node
   - (not prerelease) Download Sync Gateway RPM directly onto remote node 
5. Transfer start-sgw.sh, sg_cert.pem, sg_key.pem, bootstrap.json to the remote node
6. Uninstall any installed Sync Gateway
7. Install Sync Gateway RPM
8. Run the start-sgw.sh script (see later section for details)

## System Configuration

The configure-system.sh script does a few lightweight things to get the system ready for Sync Gateway to run.  In fact all it does is ensure the proper directories are ready to receive the various files that Sync Gateway uses to startup.

## Starting Sync Gateway

The start-sgw.sh script does a number of things in order to validate that Sync Gateway is first able to start properly, and then validate that it is running after start.  It does the following things:

1. Stops any running Sync Gateway systemd service
2. Waits for its backing Couchbase Server cluster to be responsive by checking `http://<cluster-url>:8093/admin/ping`
3. Sleeps for 5 seconds to allow the server to settle (even after ping responds, the server is still slightly unstable for a few moments)
4. Executes the Sync Gateway binary via `nohup`, using the transferred `bootstrap.json`
5. Waits for Sync Gateway to respond on localhost by checking `https://localhost:4985/_all_dbs` using the credentials `admin:password`