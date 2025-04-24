import sys
from io import TextIOWrapper
from pathlib import Path
from typing import List, cast

import pulumi_aws as aws
from pulumi import Config
from pulumi import export as pulumi_export

# This file is executed by the Pulumi CLI, so its name is important.

SCRIPT_DIR = Path(__file__).parent
if __name__ == "__main__":
    print(SCRIPT_DIR.parents[2])
    sys.path.append(str(SCRIPT_DIR.parents[2]))
    if isinstance(sys.stdout, TextIOWrapper):
        cast(TextIOWrapper, sys.stdout).reconfigure(encoding="utf-8")

from environment.aws.pulumi import constants, input_keys, output_keys

# Read the subnet in which to insert our EC2 instances.
# The mobile-e2e subnet exists in the mobile-e2e VPC and
# has domain over the IP addresses 10.0.1.1 - 10.0.1.255
# within the VPC
main = cast(
    aws.ec2.GetSubnetResult,
    aws.ec2.get_subnet_output(
        filters=[
            {
                "name": "tag:Name",
                "values": [constants.AWS_TAG_NAME],
            }
        ]
    ),
)

# The security group acts like a firewall to control which ports
# are accessible by what.  This is already created in AWS and
# named mobile-e2e so that we can retrieve it
main_get_security_group = cast(
    aws.ec2.GetSecurityGroupResult,
    aws.ec2.get_security_group_output(
        filters=[
            {
                "name": "tag:Name",
                "values": [constants.AWS_TAG_NAME],
            }
        ]
    ),
)

# Setup configuration values
config = Config()

# The name of the public key in AWS to install on the instances
key_name = config.require(input_keys.PUBLIC_KEYNAME)

# The number of Couchbase Server instances to create
server_count = config.get_int(input_keys.CBS_COUNT, 1)

# The number of Sync Gateway instances to create
sgw_count = config.get_int(input_keys.SGW_COUNT, 1)

# The number of load balancer instances to create
lb_count = config.get_int(input_keys.LB_COUNT, 0)

# Whether or not to include a logslurp deployment
wants_logslurp = config.get_bool(input_keys.WANTS_LOGSLURP, True)

# This is the machine(s) that will run Couchbase Server
cbs_instances: List[aws.ec2.Instance] = []
for i in range(0, server_count):
    cbs_instances.append(
        aws.ec2.Instance(
            f"couchbaseserver-{i}",
            ami=constants.AMAZON_LINUX_2023,
            instance_type=aws.ec2.InstanceType.M5_X_LARGE,
            key_name=key_name,
            subnet_id=main.id,
            vpc_security_group_ids=[main_get_security_group.id],
            associate_public_ip_address=True,
            root_block_device={
                "volume_size": 200,
                "volume_type": "gp2",
            },
            tags={
                "Name": "cbs",
                "Type": "couchbaseserver",
            },
        )
    )

# And the machine(s) that will run Sync Gateway
sgw_instances: List[aws.ec2.Instance] = []
for i in range(0, sgw_count):
    sgw_instances.append(
        aws.ec2.Instance(
            f"sync_gateway-{i}",
            ami=constants.AMAZON_LINUX_2023,
            instance_type=aws.ec2.InstanceType.M5_X_LARGE,
            key_name=key_name,
            subnet_id=main.id,
            vpc_security_group_ids=[main_get_security_group.id],
            associate_public_ip_address=True,
            root_block_device={
                "volume_size": 20,
                "volume_type": "gp2",
            },
            tags={
                "Name": "sg",
                "Type": "syncgateway",
            },
        )
    )

# And the machine(s) that will run load balancers
load_balancer_instances: List[aws.ec2.Instance] = []
for _ in range(0, lb_count):
    load_balancer_instances.append(
        aws.ec2.Instance(
            f"load_balancer-{i}",
            ami=constants.AMAZON_LINUX_2023,
            instance_type=aws.ec2.InstanceType.M5_LARGE,
            key_name=key_name,
            subnet_id=main.id,
            vpc_security_group_ids=[main_get_security_group.id],
            associate_public_ip_address=True,
            tags={
                "Name": "lb",
                "Type": "loadbalancer",
            },
        )
    )

# And the machine that will run LogSlurp
log_slurp = None
if wants_logslurp:
    log_slurp = aws.ec2.Instance(
        "log_slurp",
        ami=constants.AMAZON_LINUX_2023,
        instance_type=aws.ec2.InstanceType.M5_LARGE,
        key_name=key_name,
        subnet_id=main.id,
        vpc_security_group_ids=[main_get_security_group.id],
        associate_public_ip_address=True,
        tags={
            "Name": "ls",
            "Type": "logslurp",
        },
    )

pulumi_export(
    output_keys.CBS_PUBLIC_IPS, [__item.public_ip for __item in cbs_instances]
)
pulumi_export(
    output_keys.SGW_PUBLIC_IPS, [__item.public_ip for __item in sgw_instances]
)
pulumi_export(
    output_keys.LB_PUBLIC_IPS, [__item.public_ip for __item in load_balancer_instances]
)
pulumi_export(
    output_keys.CBS_PRIVATE_IPS, [__item.private_ip for __item in cbs_instances]
)
pulumi_export(
    output_keys.SGW_PRIVATE_IPS, [__item.private_ip for __item in sgw_instances]
)
pulumi_export(
    output_keys.LOG_SLURP_PUBLIC_IP, log_slurp.public_ip if log_slurp else None
)
