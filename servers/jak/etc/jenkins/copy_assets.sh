#!/bin/bash

function usage() {
    echo "Usage: $0 <src dir> <dst dir>"
    exit 1
}

if [ "$#" -ne 2 ]  ; then usage; fi

SRC="$1"
if [ -z "$SRC" ]; then usage; fi

DST="$2"
if [ -z "$DST" ]; then usage; fi


rm -rf "${DST}/3.2"
mkdir -p "${DST}/3.2"
cp -a "${SRC}/blobs" "${DST}/3.2"
cp -a "${SRC}/dbs/3.2" "${DST}/3.2/dbs"

rm -rf "${DST}/4.0"
mkdir -p "${DST}/4.0"
cp -a "${SRC}/blobs" "${DST}/4.0"
cp -a "${SRC}/dbs/4.0" "${DST}/4.0/dbs"


