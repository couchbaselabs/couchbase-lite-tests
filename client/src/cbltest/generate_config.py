import json
import os
import argparse

# Define the path to your resources and the expected config output location
POOL_JSON_PATH = "resources/pool.json"
CONFIG_JSON_PATH = "tests/config/config.json"

# Test-to-component mapping
TEST_COMPONENTS_MAPPING = {
    "sample_test": {
        "test-servers": 0,
        "sync-gateways": 1,
        "couchbase-servers": 1,
        "edge-servers": 0,
        "http-clients": 0,
    },
    "test_end_to_end": {
        "test-servers": 0,
        "sync-gateways": 1,
        "couchbase-servers": 1,
        "edge-servers": 1,
        "http-clients": 0,
    },
    "test_changes_feed": {
        "test-servers": 0,
        "sync-gateways": 1,
        "couchbase-servers": 1,
        "edge-servers": 1,
        "http-clients": 0,
    },
    "test_db_uuid": {
        "test-servers": 0,
        "sync-gateways": 0,
        "couchbase-servers": 0,
        "edge-servers": 1,
        "http-clients": 0,
    },
    "test_audit_logging": {
        "test-servers": 0,
        "sync-gateways": 1,
        "couchbase-servers": 1,
        "edge-servers": 1,
        "http-clients": 0,
    },
    "test_system": {
        "test-servers": 0,
        "sync-gateways": 1,
        "couchbase-servers": 1,
        "edge-servers": 1,
        "http-clients": 1,
    },
    "test_chaos_scenarios": {
        "test-servers": 0,
        "sync-gateways": 1,
        "couchbase-servers": 1,
        "edge-servers": 3,
        "http-clients": 5,
    },
    "test_functional": {
        "test-servers": 0,
        "sync-gateways": 1,
        "couchbase-servers": 1,
        "edge-servers": 2,
        "http-clients": 3,
    },
    "test_database_query": {
        "test-servers": 0,
        "sync-gateways": 0,
        "couchbase-servers": 0,
        "edge-servers": 1,
        "http-clients": 1,
    },
}


def load_pool_data():
    """Load IPs from pool.json"""
    with open(POOL_JSON_PATH, "r") as f:
        pool_data = json.load(f)
    return pool_data["ips"]


def generate_config(test_name, available_ips):
    """Generate config.json based on test name and available IPs."""
    if test_name not in TEST_COMPONENTS_MAPPING:
        raise Exception(f"Test name '{test_name}' not found in the mapping.")

    mapping = TEST_COMPONENTS_MAPPING[test_name]

    # Check there are enough IPs for the requested components
    if len(available_ips) < sum(mapping.values()):
        raise Exception(
            "Not enough available nodes in pool for the requested test configuration."
        )

    # Assign IPs based on the mapping
    config = {
        "$schema": "https://packages.couchbase.com/couchbase-lite/testserver.schema.json",
        "test-servers": [],
        "edge-servers": [],
        "sync-gateways": [],
        "couchbase-servers": [],
        "http-clients": [],
        "api-version": 1,
    }

    # Assign test-servers
    config["test-servers"] = [
        f"http://{ip}:8080" for ip in available_ips[: mapping["test-servers"]]
    ]
    available_ips = available_ips[mapping["test-servers"] :]

    # Assign sync-gateways
    config["sync-gateways"] = [
        {"hostname": ip} for ip in available_ips[: mapping["sync-gateways"]]
    ]
    available_ips = available_ips[mapping["sync-gateways"] :]

    # Assign couchbase-servers
    config["couchbase-servers"] = [
        {"hostname": ip} for ip in available_ips[: mapping["couchbase-servers"]]
    ]
    available_ips = available_ips[mapping["couchbase-servers"] :]

    # Assign edge-servers
    config["edge-servers"] = [
        {"hostname": ip} for ip in available_ips[: mapping["edge-servers"]]
    ]
    available_ips = available_ips[mapping["edge-servers"] :]

    # Assign http-clients
    config["http-clients"] = [
        {"hostname": ip} for ip in available_ips[: mapping["http-clients"]]
    ]

    return config


def save_config(config):
    """Save the generated config to a file."""
    os.makedirs(os.path.dirname(CONFIG_JSON_PATH), exist_ok=True)
    with open(CONFIG_JSON_PATH, "w") as f:
        json.dump(config, f, indent=4)


def main():
    parser = argparse.ArgumentParser(
        description="Generate config.json based on the test to be run."
    )
    parser.add_argument(
        "test_name",
        help="The name of the test to generate the config for (e.g., smoke_test, full_test)",
    )
    args = parser.parse_args()

    # Load available IPs from pool.json
    available_ips = load_pool_data()

    # Generate the config based on the selected test and available IPs
    config = generate_config(args.test_name, available_ips)

    # Save the generated config.json
    save_config(config)
    print(f"Config for '{args.test_name}' generated and saved to {CONFIG_JSON_PATH}")


if __name__ == "__main__":
    main()
