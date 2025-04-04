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

# Read the subnet in which to insert our EC2 instances.  
# The mobile-e2e subnet exists in the mobile-e2e VPC and
# has domain over the IP addresses 10.0.1.1 - 10.0.1.255
# within the VPC
data "aws_subnet" "main" {
    filter {
        name   = "tag:Name"
        values = ["mobile-e2e"]
    }
}

# The security group acts like a firewall to control which ports 
# are accessible by what.  This is already created in AWS and 
# named mobile-e2e so that we can retrieve it
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

# And the machine(s) that will run load balancers
resource "aws_instance" "load_balancer" {
    count = var.lb_count
    ami = "ami-05576a079321f21f8"
    instance_type = "m5.large"
    key_name = var.key_name

    subnet_id = data.aws_subnet.main.id
    vpc_security_group_ids = [data.aws_security_group.main.id]
    associate_public_ip_address = true

    tags = {
        Name = "lb"
        Type = "loadbalancer"
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

# This controls how many load balancer instances are created
variable "lb_count" {
    description = "The number of load balancer instances to create"
    type        = number
    default     = 0
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

output "load_balancer_instance_public_ips" {
    value = aws_instance.load_balancer[*].public_ip
}

output "couchbase_instance_private_ips" {
    value = aws_instance.couchbaseserver[*].private_ip
}

output "sync_gateway_instance_private_ips" {
    value = aws_instance.sync_gateway[*].private_ip
}

output "logslurp_instance_public_ip" {
    value = var.logslurp ? aws_instance.log_slurp["log_slurp"].public_ip : null
}