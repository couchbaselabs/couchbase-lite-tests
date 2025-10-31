import argparse
import json

# Load the Edge Server configuration file used
parser = argparse.ArgumentParser(
    description="Update Edge Server config with cluster IP."
)
parser.add_argument(
    "--es-config",
    required=True,
    help="Path to the Sync Gateway config template JSON file",
)
args = parser.parse_args()

# Load the cluster configuration
with open("tests/config/config.json", "r") as cluster_file:
    cluster_config = json.load(cluster_file)

# Extract the Sync Gateway IP from the cluster configuration
sync_gateway_ip = cluster_config["sync-gateways"][0]["hostname"]

# Load the Edge Server configuration template
with open(args.es_config, "r") as es_file:
    edge_server_config = json.load(es_file)

# Replace the source URL with the actual Sync Gateway IP
edge_server_config["replications"][0]["source"] = f"ws://{sync_gateway_ip}:4984/db-1"

# Save the updated Edge Server config
with open("environment/edge_server/config/config.json", "w") as updated_file:
    json.dump(edge_server_config, updated_file, indent=4)

print("Edge Server configuration updated successfully!")
