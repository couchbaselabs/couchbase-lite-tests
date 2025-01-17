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

# This is the equivalent to a docker network, essentially.
# It creates a giant block of private IP addresses, and turns
# on AWS generation of DNS hostnames (i.e. compute-1.amazonaws.com)
# It's sort of like the "ISP" of sorts
resource "aws_vpc" "main" {
    cidr_block = "10.0.0.0/16"

    enable_dns_support = true
    enable_dns_hostnames = true
    
    tags = {
        Name = "main-vpc"
    }
}

# This creates a network within the above block, which is basically
# like inserting a router into the network that has governance
# over 10.0.1.1 - 10.0.1.255
resource "aws_subnet" "main" {
    vpc_id     = aws_vpc.main.id
    cidr_block = "10.0.1.0/24"
    availability_zone = "us-east-1a"

    tags = {
        Name = "main-subnet"
    }
}

# This is like your Internet modem, it allows a network
# to be connected to the Internet.
resource "aws_internet_gateway" "main" {
    vpc_id = aws_vpc.main.id

    tags = {
        Name = "main-igw"
    }
}

# This is like a routing rule the says all outgoing traffic goes to the 
# Internet gateway.
resource "aws_route_table" "main" {
    vpc_id = aws_vpc.main.id

    route {
        cidr_block = "0.0.0.0/0"
        gateway_id = aws_internet_gateway.main.id
    }
  
    tags = {
        Name = "main-route-table"
    }
}

# This applies the above rule to the subnet so that all traffic 
# can reach the Internet.  I'm not sure if there is an improvement
# here or not regarding internal IP addresses.
resource "aws_route_table_association" "main" {
    subnet_id      = aws_subnet.main.id
    route_table_id = aws_route_table.main.id
}

# This acts like a firewall to control which ports are accessible by what
resource "aws_security_group" "main" {
    vpc_id = aws_vpc.main.id

    ingress {
        from_port   = 22
        to_port     = 22
        protocol    = "tcp"
        cidr_blocks = ["0.0.0.0/0"]
    }

    ingress {
        from_port   = 4984
        to_port     = 4986
        protocol    = "tcp"
        cidr_blocks = ["0.0.0.0/0"]
    }

    ingress {
        from_port   = 9876
        to_port     = 9876
        protocol    = "tcp"
        cidr_blocks = ["0.0.0.0/0"]
    }

    ingress {
        from_port   = 8091
        to_port     = 8096
        protocol    = "tcp"
        cidr_blocks = ["0.0.0.0/0"]
    }

    ingress {
        from_port   = 11207
        to_port     = 11207
        protocol    = "tcp"
        cidr_blocks = ["0.0.0.0/0"]
    }

    ingress {
        from_port   = 11210
        to_port     = 11211
        protocol    = "tcp"
        cidr_blocks = ["0.0.0.0/0"]
    }

    ingress {
        from_port   = 18091
        to_port     = 18096
        protocol    = "tcp"
        cidr_blocks = ["0.0.0.0/0"]
    }

    # Server node-to-node ports

    ingress {
        from_port   = 4396
        to_port     = 4396
        protocol    = "tcp"
        cidr_blocks = ["10.0.0.0/16"]
    }

    ingress {
        from_port   = 9100
        to_port     = 9105
        protocol    = "tcp"
        cidr_blocks = ["10.0.0.0/16"]
    }

    ingress {
        from_port   = 9110
        to_port     = 9118
        protocol    = "tcp"
        cidr_blocks = ["10.0.0.0/16"]
    }

    ingress {
        from_port   = 9120
        to_port     = 9122
        protocol    = "tcp"
        cidr_blocks = ["10.0.0.0/16"]
    }

    ingress {
        from_port   = 9130
        to_port     = 9130
        protocol    = "tcp"
        cidr_blocks = ["10.0.0.0/16"]
    }

    ingress {
        from_port   = 9999
        to_port     = 9999
        protocol    = "tcp"
        cidr_blocks = ["10.0.0.0/16"]
    }

    ingress {
        from_port   = 11209
        to_port     = 11210
        protocol    = "tcp"
        cidr_blocks = ["10.0.0.0/16"]
    }

    ingress {
        from_port   = 19130
        to_port     = 19130
        protocol    = "tcp"
        cidr_blocks = ["10.0.0.0/16"]
    }

    ingress {
        from_port   = 21100
        to_port     = 21100
        protocol    = "tcp"
        cidr_blocks = ["10.0.0.0/16"]
    }

    ingress {
        from_port   = 21150
        to_port     = 21150
        protocol    = "tcp"
        cidr_blocks = ["10.0.0.0/16"]
    }

    egress {
        from_port   = 0
        to_port     = 0
        protocol    = "-1"
        cidr_blocks = ["0.0.0.0/0"]
    }

    tags = {
        Name = "main-sg"
    }
}

# Finally we get to the machine that will run Couchbase Server
resource "aws_instance" "couchbaseserver" {
    ami = "ami-05576a079321f21f8"
    instance_type = "m5.xlarge"
    key_name = var.key_name

    subnet_id = aws_subnet.main.id
    vpc_security_group_ids = [aws_security_group.main.id]
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

# And the machine that will run Sync Gateway
resource "aws_instance" "sync_gateway" {
  ami = "ami-05576a079321f21f8"
    instance_type = "m5.xlarge"
    key_name = var.key_name

    subnet_id = aws_subnet.main.id
    vpc_security_group_ids = [aws_security_group.main.id]
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

# This is a variable that needs to be specified and it specifies
# the name (in AWS) of the public key that will be allowed SSH access
variable "key_name" {
    description = "The name of the EC2 key pair to use"
    type        = string
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