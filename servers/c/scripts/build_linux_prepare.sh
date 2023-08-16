#!/bin/bash -e

apt -yqq update
DEBIAN_FRONTEND=noninteractive apt -yqq install cmake build-essential