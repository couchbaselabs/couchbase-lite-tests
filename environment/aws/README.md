# AWS Scripted Backend

TL;DR This is mostly supplemental information.  If you are looking for what you need to understand to use this system, skip to [Putting it all together](#putting-it-all-together)

The summary of what is created with this area is in this diagram:

![Architecture Diagram](diagrams/Architecture.png)

The details of how this works in terms of infrastructure are in comments in the [Terraform Config File](./main.tf).  There is a lot to cover in this README so let's go section by section.  These sections are all handled automatically by the start and stop backend scripts, but this will provide some context as to what they are doing.

For more information on the specifics see the following sub README:

- [Couchbase Server Setup](./server_setup/README.md)
- [Sync Gateway Setup](./sgw_setup/README.md)
- [Log Slurp Setup](./logslurp_setup/README.md)
- [Topology Setup](./topology_setup/README.md)

## Step 0: Prerequisites

One of the core principles of making this backend work is SSH key access.  This requires that as part of deploying containers into EC2, a public key must be set up for SSH access to the various machines.  The process for doing this is [documented by Amazon](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/create-key-pairs.html) but the summary is that as part of this two very important things happen.

1. The public key gets stored on Amazon servers for deployment to EC2 containers, and it has a user-selected name that you must remember (mine is jborden, for example)
2. The private key gets stored by YOU.  Don't lose it or you will have to repeat this process.

Next, you need to make sure that the [python prerequisites](./requirements.txt) are installed in whatever environment you are using

Next, you will need to add a section to your machine SSH config (`$HOME/.ssh/config`) to ensure that public keys from AWS are automatically added to the system known hosts.  This is because the hostname will be changing every time and docker remote deploy requires an unmolested SSH connection in order to function (without adding to known_hosts you will get an interactive prompt to add the remote host to the known hosts).  To accomplish this add the following section to your SSH config:

```
Host *.amazonaws.com
    StrictHostKeyChecking accept-new
```

Finally, you will need to set up your Amazon AWS credentials so that terraform can use them.  As a Couchbase Employee the easiest way to do this is to set them up as described on the AWS SSO page that can be accessed via the Okta landing page.  The easiest result (option 2 on the resulting page) looks something like the following added to `$HOME/.aws/credentials`

```
[<redacted>_Admin]
aws_access_key_id=<redacted>
aws_secret_access_key=<redacted>
aws_session_token=<redacted>
```

> [!NOTE]  
> Using this method the credentials will only last for a few hours.  If you want a longer session than that you will need to use your long term credentials and getting them is beyond the scope of this document.  You will need to become familiar with the [IAM Section](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_credentials_access-keys.html) of AWS for that.

## Step 1: Infrastructure

It's not enough to simply spin up virtual machines.  The creator (i.e. the person modifying the [config file](./main.tf)) is responsible for basically defining the entire virtual network that the machines are located in it, including any LAN subnets and external Internet access.  The tool being used here is [Terraform](https://developer.hashicorp.com/terraform/docs), and the [config file](./main.tf) defines what resources are created when the terraform command is run.  Here is a list of what is created or read in this config file:

- Subnet covering 10.0.1.1 to 10.0.1.255 (read)
- Routing rules inside VPC for ingress and egress (read)
- x86_64 EC2 containers running AWS Linux 2 (created)

"read" here means that there is a permanent resource created in the AWS account already.  "created" means that resources must be provisioned for a particular session.

Creating and destroying these resources is as simple as running `terraform apply` and `terraform destroy` respectively.  You can add the following to avoid the console prompting you:  `-var=keyname=<keyname-from-step-0> -auto-approve`.  Other useful variables are `logslurp`, which is a bool indicating whether or not logslurp is needed, `sgw_count` which is the number of EC2 instances to create for SGW, and `server_count` which is the number of EC2 instances to create for Couchbase Server.  These default to `true`, `1`, and `1`.

## Step 2: Deployment

### AWS

Once the resources are in place, they need to have the appropriate software installed on them.  The scripts for doing so are in the `sgw_setup` (for Sync Gateway) and `server_setup` (for Couchbase Server) folders.  

The rough set of steps for Couchbase Server is as follows:

- Configure system (disable transparent huge pages and turn down swappiness as described in Couchbase docs)
- Download and install Couchbase Server RPM
- Configure node for use (init cluster, setup auth and users, etc)

For Sync Gateway:

- Download private build of SGW locally
- Upload SGW build and config files
- Create needed home directory subdirectories for config / logs
- Install and start SGW

### Test Server

This scripted backend also builds / downloads test servers for deployment to various locations that are governed by the `location` field of the topology JSON.  The `topology_setup` folder is responsible for the following:

- Build, or download, the test server with the appropriate CBL and dataset version
- Install the test server to the desired location
- Run the test server at the desired location

## Putting it all together

### Starting

```
usage: start_backend.py [-h] [--cbs-version CBS_VERSION] [--private-key PRIVATE_KEY] [--tdk-config-out TDK_CONFIG_OUT]
                        [--topology TOPOLOGY] [--no-terraform-apply] [--no-cbs-provision] [--no-sgw-provision]
                        [--no-ls-provision] [--no-ts-run] [--sgw-url SGW_URL] [--public-key-name PUBLIC_KEY_NAME]
                        --tdk-config-in TDK_CONFIG_IN

Prepare an AWS EC2 environment for running E2E tests

optional arguments:
  -h, --help            show this help message and exit
  --cbs-version CBS_VERSION
                        The version of Couchbase Server to install.
  --private-key PRIVATE_KEY
                        The private key to use for the SSH connection (if not default)
  --tdk-config-out TDK_CONFIG_OUT
                        The path to the write the resulting TDK configuration file (stdout if empty)
  --topology TOPOLOGY   The path to the topology configuration file
  --no-terraform-apply  Skip terraform apply step
  --no-cbs-provision    Skip Couchbase Server provisioning step
  --no-sgw-provision    Skip Sync Gateway provisioning step
  --no-ls-provision     Skip Logslurp provisioning step
  --no-ts-run           Skip test server install and run step

conditionally required arguments:
  --sgw-url SGW_URL     The URL of Sync Gateway to install (required if using SGW)
  --public-key-name PUBLIC_KEY_NAME
                        The public key stored in AWS that pairs with the private key (required if using any AWS
                        elements)

required arguments:
  --tdk-config-in TDK_CONFIG_IN
                        The path to the input TDK configuration file
```

The Sync Gateway URL and Couchbase Server version properties should be self explanatory but the others are as follows:

- public key name: The name of the key created in step 0
- private key: The path to the private key created in step 0 (you didn't lose it right?)
- TDK config in: A template TDK compatible config file.  
- TDK config out: An optional file to write the resulting TDK config file to (otherwise it will go to stdout)
- Topology is the toplogy JSON file that will describe how to set up AWS instances (see the [topology README](./topology_setup/README.md) for more information.)


### Stopping

```
usage: stop_backend.py [-h] [--topology TOPOLOGY]

Tear down a previously created E2E AWS EC2 testing backend

optional arguments:
  -h, --help           show this help message and exit
  --topology TOPOLOGY  The topology file that was used to start the environment
```

The stop script only has one argument which is the topology file that was used to run start_backend above.  If no file was provided to start_backend, it means the default was used and you should also give no argument to stop_backend so that it also uses the default.