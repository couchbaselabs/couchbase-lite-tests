#!/bin/bash

set -euo pipefail

echo "Resetting Couchbase cluster..."

# Wait for CBS to be ready
echo "Waiting for CBS to be ready for cluster operations..."
for i in {1..30}; do
    if curl -s http://localhost:8091/pools/default > /dev/null 2>&1; then
        break
    fi
    echo "Waiting for CBS (attempt $i/30)..."
    sleep 2
done

# Reset the cluster using couchbase-cli
echo "Resetting cluster..."
export PATH=/opt/couchbase/bin:${PATH}

/opt/couchbase/bin/couchbase-cli cluster-init \
    --cluster localhost:8091 \
    --cluster-username Administrator \
    --cluster-password password \
    --cluster-name test-cluster \
    --services data,index,query \
    --cluster-ramsize 1024 \
    --cluster-index-ramsize 256 \
    --cluster-fts-ramsize 256 \
    --index-storage-setting default || echo "Cluster may already be initialized, continuing..."

echo "Cluster reset completed."
