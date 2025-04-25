# This script is meant to be sourced into other scripts.

function create_venv() {
    if [ $# -lt 1 ]; then
        echo "Invalid call to create_venv()"
        exit 1
    fi

    PYTHON_VERSION=$(python3 -c "import sys; print('.'.join(map(str, sys.version_info[:2])))")
    REQUIRED_VERSION="3.10"

    rm -rf $1
    if [[ "$(printf '%s\n' "$REQUIRED_VERSION" "$PYTHON_VERSION" | sort -V | head -n1)" != "$REQUIRED_VERSION" ]]; then
        if command -v python$REQUIRED_VERSION &> /dev/null; then
            echo "python3 is not high enough version ($PYTHON_VERSION < $REQUIRED_VERSION)."
            echo "Using python$REQUIRED_VERSION instead."
            python${REQUIRED_VERSION} -m venv $1
        else
            echo "Error: Python $REQUIRED_VERSION or higher is required, but not found."
            echo "Checked python3 and python$REQUIRED_VERSION."
            exit 1
        fi
    else 
        echo "python3 is high enough version ($PYTHON_VERSION >= $REQUIRED_VERSION)."
        python3 -m venv $1
    fi
}