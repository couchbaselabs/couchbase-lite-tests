# AWS Scripted Backend

The summary of what is created with this area is in this diagram:

![Architecture Diagram](diagrams/Architecture.png)

The details of how this works in terms of infrastructure are in comments in the [Terraform Config File](./main.tf).  There is a lot to cover in this README so let's go section by section.  These sections are all handled automatically by the start and stop backend scripts, but this will provide some context as to what they are doing.

## Step 0: Prerequisites

One of the core principles of making this backend work is SSH key access.  This requires that as part of deploying containers into EC2, a public key must be set up for SSH access to the various machines.  The process for doing this is [documented by Amazon](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/create-key-pairs.html) but the summary is that as part of this two very important things happen.

1. The public key gets stored on Amazon servers for deployment to EC2 containers, and it has a user-selected name that you must remember (mine is jborden, for example)
2. The private key gets stored by YOU.  Don't lose it or you will have to repeat this process.

Next, you will need to run `terraform init` inside of this folder in order to set up the Terraform AWS Provider.  This only needs to be done once.

Next, you need to make sure that the [python prerequisites](./requirements.txt) are installed in whatever environment you are using

Finally, you will need to set up your Amazon AWS credentials so that terraform can use them.  As a Couchbase Employee the easiest way to do this is to set them up as described on the AWS SSO page that can be accessed via the Okta landing page.  The easiest result (option 2 on the resulting page) looks something like the following added to `$HOME/.aws/credentials`

```
[<redacted>_Admin]
aws_access_key_id=<redacted>
aws_secret_access_key=<redacted>
aws_session_token=<redacted>
```

## Step 1: Infrastructure

It's not enough to simply spin up two virtual machines.  The creator is responsible for basically definiing the entire virtual network that the machines are located in, including any LAN subnets and external Internet access.  The tool being used here is Terraform, and the [config file](./main.tf) defines what resources are created when the terraform command is run.  Here is a list of what is created in this config file:

- Virtual Private Cloud (VPC) covering IPs 10.0.0.1 to 10.0.255.255
- Subnet covering 10.0.1.1 to 10.0.1.255
- Internet Gateway (IGW)
- Routing hop from VPC to IGW
- Routing rules inside VPC for ingress and egress
- Two EC2 containers running AWS Linux 2

Creating and destroying these resources is as simple as running `terraform apply` and `terraform destroy` respectively.  You can add the following to avoid the console prompting you:  `-var=keyname=<keyname-from-step-0> -auto-approve`.

## Step 2: Deployment

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

## Putting it all together

### Starting

```
usage: start_backend.py [-h] [--cbs-version CBS_VERSION] [--sgw-version SGW_VERSION] [--sgw-build SGW_BUILD]
                        [--private-key PRIVATE_KEY] [--tdk-config-out TDK_CONFIG_OUT] --public-key-name
                        PUBLIC_KEY_NAME --tdk-config-in TDK_CONFIG_IN

Run a script over an SSH connection.

optional arguments:
  -h, --help            show this help message and exit
  --cbs-version CBS_VERSION
                        The version of Couchbase Server to install.
  --sgw-version SGW_VERSION
                        The version of Sync Gateway to install.
  --sgw-build SGW_BUILD
                        The build number of Sync Gateway to install (latest good by default)
  --private-key PRIVATE_KEY
                        The private key to use for the SSH connection (if not default)
  --tdk-config-out TDK_CONFIG_OUT
                        The path to the write the resulting TDK configuration file (stdout if empty)

required arguments:
  --public-key-name PUBLIC_KEY_NAME
                        The public key stored in AWS that pairs with the private key
  --tdk-config-in TDK_CONFIG_IN
                        The path to the input TDK configuration file
```

The version and build properties should be self explanatory but the others are as follows:

- public key name: The name of the key created in step 0
- private key: The path to the private key created in step 0 (you didn't lose it right?)
- TDK config in: A template TDK compatible config file.  