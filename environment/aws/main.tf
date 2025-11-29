terraform {
    required_providers {
      aws = {
        source  = "hashicorp/aws"
        version = "~> 4.16"
      }
      random = {
        source  = "hashicorp/random"
        version = "~> 3.4"
      }
      tls = {
        source  = "hashicorp/tls"
        version = "~> 4.0"
      }
    }

    required_version = ">= 1.2.0"
}

provider "aws" {
    region = "us-east-1"
}

# Latest Amazon Linux 2023 (x86_64)
data "aws_ami" "al2023_x86_64" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["al2023-ami-*-x86_64"]
  }
  filter {
    name   = "architecture"
    values = ["x86_64"]
  }
}

# Latest Amazon Linux 2023 (arm64 / Graviton)
data "aws_ami" "al2023_arm64" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["al2023-ami-*-arm64"]
  }
  filter {
    name   = "architecture"
    values = ["arm64"]
  }
}

# Who is running Terraform
data "aws_caller_identity" "current" {}

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

# An SSH key for connecting to the below instances

resource "tls_private_key" "ssh" {
  algorithm = "ED25519"
}

resource "random_id" "suffix" {
  byte_length = 4
}

resource "aws_key_pair" "ec2" {
    key_name = "cbs-e2e-${random_id.suffix.hex}"
    public_key = tls_private_key.ssh.public_key_openssh
    tags = {
        CreatedBy = local.created_by
    }
}

# This is the machine(s) that will run Couchbase Server
resource "aws_instance" "couchbaseserver" {
    count = var.server_count
    ami = local.ami_arm64
    instance_type = "t4g.xlarge"
    key_name = aws_key_pair.ec2.key_name

    subnet_id = data.aws_subnet.main.id
    vpc_security_group_ids = [data.aws_security_group.main.id]
    associate_public_ip_address = true

    root_block_device {
        volume_size = 50  # 50 GiB
        volume_type = "gp2"
    }

    tags = {
        Name = "cbs"
        Type = "couchbaseserver"
        ExpireAt = local.expire_at
        CreatedBy = local.created_by
    }

    lifecycle {
      ignore_changes = [ tags["ExpireAt"] ]
    }
}

# And the machine(s) that will run Sync Gateway
resource "aws_instance" "sync_gateway" {
    count = var.sgw_count
    ami = local.ami_arm64
    instance_type = "t4g.xlarge"
    key_name = aws_key_pair.ec2.key_name

    subnet_id = data.aws_subnet.main.id
    vpc_security_group_ids = [data.aws_security_group.main.id]
    associate_public_ip_address = true

    root_block_device {
        volume_size = 30  # 30 GiB (minimum required by AMI)
        volume_type = "gp2"
    }

    tags = {
        Name = "sg"
        Type = "syncgateway"
        ExpireAt = local.expire_at
        CreatedBy = local.created_by
    }

    lifecycle {
      ignore_changes = [ tags["ExpireAt"] ]
    }
}

# And the machine(s) that will run Edge Server
resource "aws_instance" "edge_server" {
    count = var.es_count
    ami = local.ami_x86_64
    instance_type = "t3a.micro"
    key_name = aws_key_pair.ec2.key_name

    subnet_id = data.aws_subnet.main.id
    vpc_security_group_ids = [data.aws_security_group.main.id]
    associate_public_ip_address = true

    tags = {
        Name = "es"
        Type = "edgeserver"
        ExpireAt = local.expire_at
        CreatedBy = local.created_by
    }

    lifecycle {
      ignore_changes = [ tags["ExpireAt"] ]
    }
}

# And the machine(s) that will run load balancers
resource "aws_instance" "load_balancer" {
    count = var.lb_count
    ami = local.ami_arm64
    instance_type = "t4g.medium"
    key_name = aws_key_pair.ec2.key_name

    subnet_id = data.aws_subnet.main.id
    vpc_security_group_ids = [data.aws_security_group.main.id]
    associate_public_ip_address = true

    tags = {
        Name = "lb"
        Type = "loadbalancer"
        ExpireAt = local.expire_at
        CreatedBy = local.created_by
    }

    lifecycle {
      ignore_changes = [ tags["ExpireAt"] ]
    }
}

# And the machine that will run LogSlurp
resource "aws_instance" "log_slurp" {
    for_each = var.logslurp ? { "log_slurp": 1 } : {}
    ami = local.ami_arm64
    instance_type = "t4g.medium"
    key_name = aws_key_pair.ec2.key_name

    subnet_id = data.aws_subnet.main.id
    vpc_security_group_ids = [data.aws_security_group.main.id]
    associate_public_ip_address = true

    tags = {
        Name = "ls"
        Type = "logslurp"
        ExpireAt = local.expire_at
        CreatedBy = local.created_by
    }

    lifecycle {
      ignore_changes = [ tags["ExpireAt"] ]
    }
}

locals {
  arn_path_parts = split("/", data.aws_caller_identity.current.arn)
  created_by     = local.arn_path_parts[length(local.arn_path_parts)-1]
  expire_at = formatdate(
    "YYYY-MM-DD'T'hh:mm:ss'Z'",
    timeadd(timestamp(), format("%dh", 3 * 24))
  )
  ami_x86_64 = data.aws_ami.al2023_x86_64.id
  ami_arm64  = data.aws_ami.al2023_arm64.id
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

# This controls how many Edge Server instances are created
variable "es_count" {
    description = "The number of Edge Server instances to create"
    type        = number
    default     = 0
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

output "edge_server_instance_public_ips" {
    value = aws_instance.edge_server[*].public_ip
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

output "edge_server_instance_private_ips" {
    value = aws_instance.edge_server[*].private_ip
}

output "logslurp_instance_public_ip" {
    value = var.logslurp ? aws_instance.log_slurp["log_slurp"].public_ip : null
}

output "private_key_material" {
    value = tls_private_key.ssh.private_key_openssh
    sensitive = true
}
