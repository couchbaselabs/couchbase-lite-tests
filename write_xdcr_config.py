#!/usr/bin/env python3

import json
import subprocess
import pathlib

SCRIPT_DIR = pathlib.Path(__file__).parent.resolve()

def main():
    write_pytest_config(xdcr=True)

def get_ip(container_name: str) -> str:
    ip_addr = subprocess.run(
        [
            "docker",
            "inspect",
            "-f",
            "{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}",
            container_name,
        ],
        stdout=subprocess.PIPE,
        check=True,
        text=True,
    ).stdout.strip()
    return ip_addr


def write_pytest_config(*, xdcr=True) -> pathlib.Path:
    CBS_USERNAME = "Administrator"
    CBS_PASSWORD = "password"

    config = {
        "test-servers": [
            "http://localhost:8080",
        ],
        "sync-gateways": [],
        "couchbase-servers": [],
        "api-version": 1,
    }
    cbs_hostnames = ["localhost"]
    sg_hostnames = ["localhost"]
    if xdcr:
        cbs1_ip = get_ip("environment-cbl-test-cbs1-1")
        cbs2_ip = get_ip("environment-cbl-test-cbs2-1")
        sg1_ip = get_ip("environment-cbl-test-sg1-1")
        sg2_ip = get_ip("environment-cbl-test-sg2-1")
        nginx_ip = get_ip('environment-cbl-test-nginx-1')

        print(f"Created cluster1 with CBS: {cbs1_ip} and SG: {sg1_ip}")
        print(f"Created cluster2 with CBS: {cbs2_ip} and SG: {sg2_ip}")
        print(
            f"Created load balancer with IP: {nginx_ip}"
        )
        cbs_hostnames = [cbs1_ip, cbs2_ip]
        sg_hostnames = [sg1_ip, sg2_ip, nginx_ip]
        config["sg-load-balancer"] = nginx_ip

    for cbs_hostname in cbs_hostnames:
        config["couchbase-servers"].append(
            {
                "hostname": cbs_hostname,
                "admin_user": CBS_USERNAME,
                "admin_password": CBS_PASSWORD,
                "tls": False,
            }
        )
    for sg_hostname in sg_hostnames:
        config["sync-gateways"].append(
            {
                "hostname": sg_hostname,
                "port": 4984,
                "admin_port": 4985,
                "rbac_user": CBS_USERNAME,
                "rbac_password": CBS_PASSWORD,
                "tls": False,
            }
        )

    filename = SCRIPT_DIR / "tests/xdcr_config.json"
    with open(filename, "w") as f:
        json.dump(config, f, indent=4)
    return filename

if __name__ == "__main__":
    main()
