terraform {
    required_providers {
      aws = {
        source  = "hashicorp/aws"
        version = "~> 4.16"
      }
    }

    required_version = ">= 1.2.0"
}

provider "aws" {
    region = "us-east-1"
}

# This is all stuff that is already set up, we just need
# to make terraform aware of it

# The VPC is the equivalent to a docker network, essentially.
# It has a giant block of private IP addresses, and turns
# on AWS generation of DNS hostnames (i.e. compute-1.amazonaws.com)
# It's sort of like the "ISP" of sorts
data "aws_vpc" "main" {
    filter {
        name   = "tag:Name"
        values = ["mobile-e2e"]
    }
}

# The subnet is a network within the above block, which is basically
# like inserting a router into the network that has governance
# over (in our case) 10.0.1.1 - 10.0.1.255
data "aws_subnet" "main" {
    filter {
        name   = "tag:Name"
        values = ["mobile-e2e"]
    }
}

# The security group acts like a firewall to control which ports 
# are accessible by what
data "aws_security_group" "main" {
    filter {
        name   = "tag:Name"
        values = ["mobile-e2e"]
    }
}

# Below are the resources that we will create

# This is the machine(s) that will run Couchbase Server
resource "aws_instance" "couchbaseserver" {
    count = var.server_count
    ami = "ami-05576a079321f21f8"
    instance_type = "m5.xlarge"
    key_name = var.key_name

    subnet_id = data.aws_subnet.main.id
    vpc_security_group_ids = [data.aws_security_group.main.id]
    associate_public_ip_address = true

    root_block_device {
        volume_size = 200  # 200 GiB
        volume_type = "gp2"
    }

    tags = {
        Name = "cbs"
        Type = "couchbaseserver"
    }
}

# And the machine(s) that will run Sync Gateway
resource "aws_instance" "sync_gateway" {
    count = var.sgw_count
    ami = "ami-05576a079321f21f8"
    instance_type = "m5.xlarge"
    key_name = var.key_name

    subnet_id = data.aws_subnet.main.id
    vpc_security_group_ids = [data.aws_security_group.main.id]
    associate_public_ip_address = true

    root_block_device {
        volume_size = 20  # 20 GiB
        volume_type = "gp2"
    }

    tags = {
        Name = "sg"
        Type = "syncgateway"
    }
}

# And the machine that will run LogSlurp
resource "aws_instance" "log_slurp" {
    for_each = var.logslurp ? { "log_slurp": 1 } : {}
    ami = "ami-05576a079321f21f8"
    instance_type = "m5.large"
    key_name = var.key_name

    subnet_id = data.aws_subnet.main.id
    vpc_security_group_ids = [data.aws_security_group.main.id]
    associate_public_ip_address = true

    tags = {
        Name = "ls"
        Type = "logslurp"
    }
}

# This is a variable that needs to be specified and it specifies
# the name (in AWS) of the public key that will be allowed SSH access
variable "key_name" {
    description = "The name of the EC2 key pair to use"
    type        = string
}

# This controls how many Couchbase Server instances are created
variable "server_count" {
    description = "The number of Couchbase Server instances to create"
    type        = number
    default     = 1
}

# This controls how many Sync Gateway instances are created
variable "sgw_count" {
    description = "The number of Sync Gateway instances to create"
    type        = number
    default     = 1
}

# This controls whether or not to include a LogSlurp instance
variable "logslurp" {
    description = "Whether or not to include a logslurp deployment"
    type = bool
    default = true
}

# These outputs are convenient for scripts to use for writing various IPs
# to be used in config files, etc
output "couchbase_instance_public_ips" {
    value = aws_instance.couchbaseserver[*].public_ip
}

output "sync_gateway_instance_public_ips" {
    value = aws_instance.sync_gateway[*].public_ip
}

output "couchbase_instance_private_ips" {
    value = aws_instance.couchbaseserver[*].private_ip
}

output "logslurp_instance_public_ip" {
    value = var.logslurp ? aws_instance.log_slurp["log_slurp"].public_ip : null
}