#!/bin/sh

rm -rf cmake
mkdir -p cmake
pushd cmake > /dev/null
cmake ../../../vendor
popd cmake > /dev/null 
