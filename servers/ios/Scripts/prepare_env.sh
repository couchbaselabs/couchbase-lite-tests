#!/bin/bash -e

function usage() {
    echo "Usage: $0 <dataset-version: 3.2 | 4.0>"
    exit 1
}

if [ "$#" -lt 1 ]; then
    usage
fi

DATASET_VERSION=${1}

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
DATASET_BASE_DIR=$(realpath "${SCRIPT_DIR}/../../../dataset/server")
DATASET_DBS_DIR="${DATASET_BASE_DIR}/dbs/${DATASET_VERSION}"
DATASET_BLOB_DIR="${DATASET_BASE_DIR}/blobs"
ASSETS_DIR="${SCRIPT_DIR}/../Assets"

# Change to the assets directory and clean up
pushd "${ASSETS_DIR}" > /dev/null
rm -rf dbs && mkdir dbs
rm -rf blobs && mkdir blobs

# Copy databases and blobs
echo "Copying databases from ${DATASET_DBS_DIR}"
cp "${DATASET_DBS_DIR}"/* dbs

echo "Copying blobs from ${DATASET_BLOB_DIR}"
cp "${DATASET_BLOB_DIR}"/* blobs
