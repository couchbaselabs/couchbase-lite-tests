# Edge Server AWS setup

The contents of this folder all have to do with deploying and setting up Edge Server onto one or more AWS nodes so that at the end it is ready to go for E2E testing.  The steps that it takes are as follows:

1. (if prerelease build) Download Edge Server RPM from latestbuilds
2. Transfer configure-system.sh to remote node
3. Run configure-system.sh (see later section for details)
4. Depending on if the desired Edge Server version is prerelease or not
   - (prerelease) Transfer Edge Server RPM to remote node
   - (not prerelease) Download Edge Server RPM directly onto remote node 
5. Generate key and certificate es_key.pem and es_cert.pem
6. Transfer start-es.sh, es_cert.pem, es_key.pem, es_config.json to the remote node
7. Uninstall any installed Edge Server
8. Install Edge Server RPM
9. Run the start-es.sh script (see later section for details)

## System Configuration

The configure-system.sh script does a few lightweight things to get the system ready for Edge Server to run.  In fact all it does is ensure the proper directories are ready to receive the various files that Edge Server uses to startup.

## Starting Edge Server

The start-es.sh script does a number of things in order to validate that Edge Server is first able to start properly, and then validate that it is running after start.  It does the following things:

1. Stops any running Edge Server systemd service
2. Executes the Edge Server binary via `setsid`, using the transferred `es_config.json`
3. Waits for Edge Server to respond on localhost by checking `https://localhost:59840/_all_dbs`