#!/usr/bin/env python3

import json
import subprocess
import pathlib
import shutil
import time

DATASET_VERSION = "4.0"
COUCHBASE_LITE_VERSION = "4.0.0"
COUCHBASE_LITE_BUILD_NUMBER = "7"

SCRIPT_DIR = pathlib.Path(__file__).parent.resolve()
TEST_SERVER = SCRIPT_DIR / "servers" / "c" / "build" / "out" / "bin" / "testserver"


def build_test_server(*, force=False, clean_build=False):
    if not force and TEST_SERVER.exists():
        return
    if clean_build:
        build_dir = SCRIPT_DIR / "servers" / "c"
        shutil.rmtree(build_dir)
    cmd = f"./servers/c/scripts/build_macos.sh enterprise {COUCHBASE_LITE_VERSION} {COUCHBASE_LITE_BUILD_NUMBER} {DATASET_VERSION}"
    print(cmd)
    subprocess.run(cmd, shell=True, cwd=SCRIPT_DIR)


def main():
    create_dinonet()
    build_test_server()
    testserver_log = (SCRIPT_DIR / "testserver1.log").open("w")
    try:
        testserver_proc = subprocess.Popen(
            [str(TEST_SERVER)],
            stdout=testserver_log,
            stderr=subprocess.STDOUT,
            cwd=SCRIPT_DIR / "servers" / "c",
        )

        xdcr = True
        start_couchbase_cluster(xdcr=True)
        config = write_pytest_config(xdcr=True)
        cmd = [
            "pytest",
            "--config",
            str(config),
            "tests/test_basic_replication_xdcr.py",
            "-k",
            "test_push_with_xdcr",
            "-s",
            "-x",
            "-o",
            "log_cli=true",
        ]
        print(f"Running {' '.join(cmd)}")
        subprocess.run(cmd, cwd=SCRIPT_DIR)
    finally:
        testserver_proc.terminate()
        testserver_log.close()


def start_test_server():
    testserver_proc = subprocess.run([str(TEST_SERVER)])
    pass


def start_couchbase_cluster(xdcr=True):
    filename = SCRIPT_DIR / "environment" / "docker-compose.yml"
    if xdcr:
        filename = SCRIPT_DIR / "environment" / "docker-compose-xdcr.yml"
    subprocess.call(
        [
            "docker",
            "compose",
            "-f",
            filename,
            "up",
            "--build",
            "--remove-orphans",
            "--detach",
            "--wait",
        ],
    )


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


def create_dinonet():
    """
    Create dinonet that is shared with cbdinocluster, in case that is already running.
    """
    networks = subprocess.run(
        [
            "docker",
            "network",
            "ls",
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if "dinonet" in networks:
        return
    colima_addr = subprocess.run(
        [
            "colima",
            "ls",
            "-j",
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    colima_addr = json.loads(colima_addr)["address"]
    prefix = ".".join(colima_addr.split(".")[0:3])
    subnet = prefix + ".0/24"
    ip_range = prefix + ".128/25"
    gateway = prefix + ".1"
    cmd = [
        "docker",
        "network",
        "create",
        "dinonet",
        "--driver",
        "ipvlan",
        "--subnet",
        subnet,
        "--gateway",
        gateway,
        "--ip-range",
        ip_range,
        "--opt",
        "parent=col0",
    ]
    print(f"Creating dinonet with cmd: {' '.join(cmd)}")
    subprocess.run(cmd, check=True)


if __name__ == "__main__":
    main()
