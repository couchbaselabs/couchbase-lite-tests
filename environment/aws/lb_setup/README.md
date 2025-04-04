# Load Balancer AWS setup

The contents of this folder all have to do with deploying and setting up one or more load balancers onto one or more AWS nodes so that at the end it is ready to go for E2E testing.  The steps that it takes are as follows:

1. Transfer configure-system.sh to the remote node
2. Run configure-system.sh (see later section for details)
3. Sets up a local docker context that runs over SSH to the remote node
4. Starts a docker container of nginx, or uses an existing one that it finds

## System Configuration

The AWS remote node is not going to have docker installed by default, so the configure-system.sh will do the following:

1. If docker is not found, install docker via yum and start its systemd service
2. If the user is not a member of the docker group, add the user to the docker group so that the user can run docker commands without sudo.