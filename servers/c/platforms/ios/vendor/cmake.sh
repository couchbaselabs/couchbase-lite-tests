#!/bin/sh

rm -rf cmake
mkdir -p cmake
pushd cmake > /dev/null
cmake CMAKE_BUILD_TYPE=Release ../../../../vendor
popd cmake > /dev/null 
