# This script is meant to be sourced into other scripts.

PYTHON_VERSION=$(python3 -c "import sys; print('.'.join(map(str, sys.version_info[:2])))")
REQUIRED_VERSION="3.10"

if [[ "$(printf '%s\n' "$REQUIRED_VERSION" "$PYTHON_VERSION" | sort -V | head -n1)" != "$REQUIRED_VERSION" ]]; then
    if command -v python$REQUIRED_VERSION &> /dev/null; then
        echo "python3 is not high enough version ($PYTHON_VERSION < $REQUIRED_VERSION)."
        echo "Using python$REQUIRED_VERSION instead."
        alias python3="python$REQUIRED_VERSION"
    else
        echo "Error: Python $REQUIRED_VERSION or higher is required, but not found."
        echo "Checked python3 and python3.10."
        exit 1
    fi
fi