import json

# Paths to the configuration files
CLUSTER_CONFIG_PATH = 'tests/config/config.json'  # Cluster config file
SG_CONFIG_TEMPLATE_PATH = 'environment/sg/config/bootstrap_sample.json'  # Sync Gateway config template
UPDATED_SG_CONFIG_PATH = 'environment/sg/config/bootstrap.json'  # Updated Sync Gateway config

# Load the cluster config to extract Couchbase IP
with open(CLUSTER_CONFIG_PATH, 'r') as cluster_file:
    cluster_config = json.load(cluster_file)

# Extract the Couchbase IP from the cluster config (first "couchbase-servers" entry)
couchbase_ip = cluster_config["couchbase-servers"][0]["hostname"]

# Check if Couchbase IP was extracted successfully
if not couchbase_ip:
    print("Error: Couchbase IP not found in the cluster config.")
    exit(1)

print(f"Couchbase IP: {couchbase_ip}")

# Load the Sync Gateway configuration template
with open(SG_CONFIG_TEMPLATE_PATH, 'r') as sg_file:
    sg_config = json.load(sg_file)

# Update the "server" field under "bootstrap" with the Couchbase IP
sg_config["bootstrap"]["server"] = f"couchbases://{couchbase_ip}"

# Save the updated Sync Gateway config to a new file
with open(UPDATED_SG_CONFIG_PATH, 'w') as updated_file:
    json.dump(sg_config, updated_file, indent=4)

print("Sync Gateway configuration updated successfully!")
