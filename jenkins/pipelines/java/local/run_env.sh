#!/bin/bash

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
ROOT_DIR="${SCRIPT_DIR}"/../../../..

SG_URL="$1"

cd "${ROOT_DIR}"/jenkins/pipelines/shared/
./setup_backend.sh "${SG_URL}"

