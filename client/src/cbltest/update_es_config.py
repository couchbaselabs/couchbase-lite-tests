import json

# Load the cluster configuration
with open('tests/config/config.json', 'r') as cluster_file:
    cluster_config = json.load(cluster_file)

# Extract the Sync Gateway IP from the cluster configuration
sync_gateway_ip = cluster_config["sync-gateways"][0]["hostname"]

# Load the Sync Gateway configuration template
with open('environment/edge_server/config/config_sample.json', 'r') as sg_file:
    sync_gateway_config = json.load(sg_file)

# Replace the source URL with the actual Sync Gateway IP
sync_gateway_config["replications"][0]["source"] = f"ws://{sync_gateway_ip}:4984/db-1"

# Save the updated Sync Gateway config
with open('environment/edge_server/config/config.json', 'w') as updated_file:
    json.dump(sync_gateway_config, updated_file, indent=4)

print("Edge Server configuration updated successfully!")
