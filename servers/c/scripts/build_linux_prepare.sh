#!/bin/bash -e

apt -yqq update
DEBIAN_FRONTEND=noninteractive apt -yqq install curl cmake build-essential zlib1g-dev