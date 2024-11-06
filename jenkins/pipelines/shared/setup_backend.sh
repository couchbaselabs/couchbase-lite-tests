#!/bin/bash -e

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )

if test -t 1; then
    ncolors=$(tput colors)
    if test -n "$ncolors" && test $ncolors -ge 8; then
        BOLD="$(tput bold)"
        UNDERLING="$(tput smul)"
        STANDOUT="$(tput smso)"
        NORMAL="$(tput sgr0)"
        black="$(tput setaf 0)"
        RED="$(tput setaf 1)"
        GREEN="$(tput setaf 2)"
        YELLOW="$(tput setaf 3)"
        BLUE="$(tput setaf 4)"
        MAGENTA="$(tput setaf 5)"
        CYAN="$(tput setaf 6)"
        WHITE="$(tput setaf 7)"
    fi
fi

function write-banner() {
    echo
    echo ${GREEN}===== $1 =====${NORMAL}
    echo
}

sgw_url=""
if [ $# -eq 1 ]; then
    sgw_url=$1
fi

write-banner "Stopping existing environment"
pushd $SCRIPT_DIR/../../../environment
docker compose down # Just in case it didn't get shut down cleanly

write-banner "Building Couchbase Server Image"
docker compose build cbl-test-cbs

write-banner "Building logslurp Image"
docker compose build cbl-test-logslurp

if [ "$sgw_url" != "" ]; then
    write-banner "Building Sync Gateway Image"
    docker compose build cbl-test-sg --build-arg SG_DEB="$sgw_url"
fi

write-banner "Starting Backend"
./start_environment.py
