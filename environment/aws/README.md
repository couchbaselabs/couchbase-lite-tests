# AWS Scripted Backend

**TL;DR This is mostly supplemental information.  If you are looking for what you need to understand to use this system, skip to [Prerequisites](#prerequisites) and [Putting it all together](#putting-it-all-together)**

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

### libimobiledevice (iOS only)

You need to install this package from homebrew as it is a dependency for the iOS IP discovery process

### XHarness (optional, iOS only)

If you are working with devices that are iOS 16.x or lower you will need to install [XHarness](https://github.com/dotnet/xharness)

## Infrastructure Deep Dive

Skip to [Putting it all together](#putting-it-all-together) if you are just after how to run the orchestrator.

It's not enough to simply spin up virtual machines.  The creator (i.e. the person modifying the [config file](./main.tf)) is responsible for basically defining the entire virtual network that the machines are located in it, including any LAN subnets and external Internet access.  The tool being used here is [Terraform](https://developer.hashicorp.com/terraform/docs), and the [config file](./main.tf) defines what resources are created when the terraform command is run.  Here is a list of what is created or read in this config file:

- Subnet covering 10.0.1.1 to 10.0.1.255 (read)
- Routing rules inside VPC for ingress and egress (read)
- Graviton EC2 containers running AWS Linux 2023 (created)

"read" here means that there is a permanent resource created in the AWS account already.  "created" means that resources must be provisioned for a particular session.

Creating and destroying these resources is as simple as running `terraform apply` and `terraform destroy` respectively.  You can add `-auto-approve` to avoid the console prompting you.  The SSH key pair is generated automatically by Terraform (`aws_key_pair.ec2`) — there is no `keyname` variable to set.  Other useful variables are `logslurp`, which is a bool indicating whether or not logslurp is needed, `sgw_count` which is the number of EC2 instances to create for SGW, and `server_count` which is the number of EC2 instances to create for Couchbase Server.  These default to `true`, `1`, and `1`.

## Deployment

Skip to [Putting it all together](#putting-it-all-together) if you are just after how to run the orchestrator.

### AWS

Once the resources are in place, they need to have the appropriate software installed on them.  For example, the scripts for doing so for Sync Gateway and Couchbase Server are in the `sgw_setup` (for Sync Gateway) and `server_setup` (for Couchbase Server) folders.  There are other folders that have "setup" in their name which address other things like LogSlurp, Edge Server, etc.

The rough set of steps for Couchbase Server is as follows:

- Configure system (install Docker, sudoers rules for the `couchbase-server` service, Caddy/shell2http)
- Run Couchbase Server as a Docker container (`couchbase/server:enterprise-<version>`)
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

Starting and stopping the system has dedicated python scripts.

These scripts are designed to be run either via `uv run`, or imported and called from another python script if desired.  If you skipped here from the beginning, be sure to review the [Prerequisites](#prerequisites).

### Starting

```
Usage: start_backend.py [OPTIONS]

  Prepare an AWS EC2 environment for running E2E tests.

Options:
  --topology TOPOLOGY    The path to the topology configuration file
  --tdk-config-in PATH   The path to the input (template) TDK configuration file  [required]
  --tdk-config-out PATH  The path to write the resulting TDK configuration file (stdout if empty)
  --no-terraform-apply   Skip terraform apply step
  --no-cbs-provision     Skip Couchbase Server provisioning step
  --no-sgw-provision     Skip Sync Gateway provisioning step
  --no-es-provision      Skip Edge Server provisioning step
  --no-lb-provision      Skip load balancer provisioning step
  --no-ls-provision      Skip LogSlurp provisioning step
  --no-ts-run            Skip test server install and run step
  --help                 Show this message and exit
```

The main arguments are:

- TDK config in: A template TDK-compatible config file (required).
- TDK config out: An optional file to write the resulting TDK config to (otherwise it goes to stdout).
- Topology: The topology JSON file describing how to set up the AWS instances (see the [topology README](./topology_setup/README.md) for more information).

> **Note:** Couchbase Server and Sync Gateway versions are no longer set on the command line. They now come from the topology file — `defaults.cbs.version` / `defaults.sgw.version`, or the per-cluster / per-gateway `version` fields. The `--no-*-provision` flags let you stand up only a subset of the environment.


### Stopping

```
Usage: stop_backend.py [OPTIONS]

Options:
  --topology PATH      The topology file that was used to start the
                       environment
  --destroy-sgw        Destroy only Sync Gateway instances
  --sgw-index INTEGER  Specific SGW instance index to destroy (0-based, only
                       with --destroy-sgw)
  --destroy-cbs        Destroy only Couchbase Server instances
  --destroy-es         Destroy only Edge Server instances
  --destroy-lb         Destroy only Load Balancer instances
  --destroy-ls         Destroy only Logslurp instances
  --no-ts-stop         Do not stop test servers
  --no-full-destroy    Do not destroy all terraform managed resources if no
                       specific component is selected
  --help               Show this message and exit.
```

`--topology` should point at the same topology file used to run `start_backend.py` above (default if none was given).  Without any `--destroy-*` flag, `stop_backend.py` runs a full `terraform destroy`; the `--destroy-*` flags target individual components instead, and `--no-ts-stop`/`--no-full-destroy` narrow the teardown further.
