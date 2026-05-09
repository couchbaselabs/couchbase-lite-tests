SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ -z "$TS_PLATFORM" ]; then
    echo "Error: TS_PLATFORM environment variable is not set."
    return
fi

source "$SCRIPT_DIR/../shared/config.sh"
if [[ "$TS_PLATFORM" == dotnet* ]]; then
    source $SCRIPT_DIR/setup_dotnet.sh
fi