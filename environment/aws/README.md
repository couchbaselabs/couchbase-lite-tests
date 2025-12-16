# AWS Scripted Backend

**TL;DR This is mostly supplemental information.  If you are looking for what you need to understand to use this system, skip to [Prerequisites](#step-0-prerequisites) and [Putting it all together](#putting-it-all-together)**

The way it works from a high level is as follows.  The starting point is an environment set up as in the following:

![Architecture Start](diagrams/architecture-1.png)

Inside of the control machine there are two components.  The TDK is responsible for executing tests and the orchestrator is responsible for setting them up.  When setting up, the orchestrator first creates the proper number of instance in Amazon EC2 inside of a pre-created virtual subnet:

![Architecture Phase 2](diagrams/architecture-2.png)

The next thing it does is install the appropriate software onto each of the EC2 nodes, and install the desired variant of the test server onto the mobile device:

![Architecture Phase 3](diagrams/architecture-3.png)

And at the end the TDK will be able to communicate with all of the pieces that were set up:

![Architecture Final](diagrams/architecture-4.png)

The details of how this works in terms of infrastructure are in comments in the [Terraform Config File](./main.tf).  There is a lot to cover in this README so let's go section by section.  These sections are all handled automatically by the start and stop backend scripts, but this will provide some context as to what they are doing.

For more information on the specifics see the following sub README:

- [Couchbase Server Setup](./server_setup/README.md)
- [Sync Gateway Setup](./sgw_setup/README.md)
- [Log Slurp Setup](./logslurp_setup/README.md)
- [Topology Setup](./topology_setup/README.md)

## Prerequisites

### AWS SSO Configuration

You need to configure the aws CLI to login with Okta.  You can do so by following the steps on the internal [wiki page](https://confluence.issues.couchbase.com/wiki/spaces/cbeng/pages/3243114500/AWS+access) on the topic.  Specifically for the TDK, pay attention to what you choose as the profile name.  You have two choices here:

1. Choose "default" as the profile name, and then you are done (this will have an effect on any existing AWS config you have so be careful)
2. Choose any other profile name, including the default provided one, and set it in the environment variable `AWS_PROFILE` before running the orchestrator

### Python dependencies

First of all you need to be using Python 3.10 or higher, but less than 3.13 (it might work but it's been known to cause issues sometimes).  You also need to make sure that the [python dependencies](./requirements.txt) are installed in whatever environment you are using.  If you know nothing about python that means that when you use this orchestration you need to run `pip install -r requirements.txt` before trying to do anything, so that its dependencies are installed.  The most sane way to do this is to install [uv](https://docs.astral.sh/uv/getting-started/installation/) and then run the following:

```
uv venv --python 3.10
source .venv/bin/activate
uv pip install -r requirements.txt
```

### SSH configuration

You will need to add a section to your machine SSH config (`$HOME/.ssh/config`) to ensure that public keys from AWS are automatically added to the system known hosts.  This is because the hostname will be changing every time and docker remote deploy requires an unmolested SSH connection in order to function (without adding to known_hosts you will get an interactive prompt to add the remote host to the known hosts).  To accomplish this add the following section to your SSH config:

```
Host *.amazonaws.com
    StrictHostKeyChecking accept-new
```

Furthermore, you will need to set the default key for these addresses to be the key you intend to use to connect to the EC2 instances (i.e. the private key you created above).  If it's your default key (id_rsa, etc) then this step is not needed but that's not usually the case.  This is to work around a docker limitation that doesn't allow specifying a key when it connects via ssh.

```
Host *.amazonaws.com
    StrictHostKeyChecking accept-new
    IdentityFile <path/to/key>
```

### Git LFS

As stated in the top level README of this repo, Git LFS must be installed so that the datasets and blobs are properly pulled for building test servers.  

### Terraform

The AWS instances are set up using [terraform](https://developer.hashicorp.com/terraform/install), so it must be installed.

### Xcode 16.0 or higher (iOS only)

This is required because of a command usage that was introduced in this version of Xcode.  Your best bet is to simply install the latest version of Xcode.

### iPhone Private WiFi (iOS only)

The "Private Wi-Fi Address" setting of any iOS devices intended to be used *must* be set to `Off` for auto detection of iOS device IP addresses to work.

### libimobiledevice and arping (iOS only)

You need to install these packages from homebrew as they are dependencies for the iOS IP discovery process

### XHarness (optional, iOS only)

If you are working with devices that are iOS 16.x or lower you will need to install [XHarness](https://github.com/dotnet/xharness)

## Infrastructure Deep Dive

Skip to [Putting it all together](#putting-it-all-together) if you are just after how to run the orchestrator.  

It's not enough to simply spin up virtual machines.  The creator (i.e. the person modifying the [config file](./main.tf)) is responsible for basically defining the entire virtual network that the machines are located in it, including any LAN subnets and external Internet access.  The tool being used here is [Terraform](https://developer.hashicorp.com/terraform/docs), and the [config file](./main.tf) defines what resources are created when the terraform command is run.  Here is a list of what is created or read in this config file:

- Subnet covering 10.0.1.1 to 10.0.1.255 (read)
- Routing rules inside VPC for ingress and egress (read)
- Graviton EC2 containers running AWS Linux 2023 (created)

"read" here means that there is a permanent resource created in the AWS account already.  "created" means that resources must be provisioned for a particular session.

Creating and destroying these resources is as simple as running `terraform apply` and `terraform destroy` respectively.  You can add the following to avoid the console prompting you:  `-var=keyname=<keyname-from-step-0> -auto-approve`.  Other useful variables are `logslurp`, which is a bool indicating whether or not logslurp is needed, `sgw_count` which is the number of EC2 instances to create for SGW, and `server_count` which is the number of EC2 instances to create for Couchbase Server.  These default to `true`, `1`, and `1`.

## Deployment

Skip to [Putting it all together](#putting-it-all-together) if you are just after how to run the orchestrator.

### AWS

Once the resources are in place, they need to have the appropriate software installed on them.  For example, the scripts for doing so for Sync Gateway and Couchbase Server are in the `sgw_setup` (for Sync Gateway) and `server_setup` (for Couchbase Server) folders.  There are other folders that have "setup" in their name which address other things like LogSlurp, Edge Server, etc.

The rough set of steps for Couchbase Server is as follows:

- Configure system (disable transparent huge pages and turn down swappiness as described in Couchbase docs)
- Download and install Couchbase Server RPM
- Configure node for use (init cluster, setup auth and users, etc)

For Sync Gateway:

- Download private build of SGW locally
- Upload SGW build and config files
- Create needed home directory subdirectories for config / logs
- Install and start SGW

Various Others:

- Install docker on EC2
- Start a container of a given image via docker SSH context

### Test Server

This scripted backend also builds / downloads test servers for deployment to various locations that are governed by the `location` field of the topology JSON.  The `topology_setup` folder is responsible for the following:

- Build, or download, the test server with the appropriate CBL and dataset version
- Install the test server to the desired location
- Run the test server at the desired location

## Putting it all together

Starting and stopping the system has dedicated python scripts.  These scripts are designed to be run either directly, or imported and called from another python script if desired.  If you skipped here from the beginning, be sure to review the [Prerequisites](#step-0-prerequisites).

### Starting

```
usage: start_backend.py [-h] [--cbs-version CBS_VERSION] [--tdk-config-out TDK_CONFIG_OUT]
                        [--topology TOPOLOGY] [--no-terraform-apply] [--no-cbs-provision] [--no-sgw-provision]
                        [--no-ls-provision] [--no-ts-run] [--sgw-url SGW_URL]
                        --tdk-config-in TDK_CONFIG_IN

Prepare an AWS EC2 environment for running E2E tests

optional arguments:
  -h, --help            show this help message and exit
  --cbs-version CBS_VERSION
                        The version of Couchbase Server to install.
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

required arguments:
  --tdk-config-in TDK_CONFIG_IN
                        The path to the input TDK configuration file
```

The Sync Gateway URL and Couchbase Server version properties should be self explanatory but the others are as follows:

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
