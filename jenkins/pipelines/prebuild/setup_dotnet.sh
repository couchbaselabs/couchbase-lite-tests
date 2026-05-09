SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

function prepare_dotnet() {
    source $SCRIPT_DIR/../dev_e2e/dotnet/prepare_env.sh
    install_dotnet "$DOTNET_SDK_VERSION"
}

prepare_dotnet
export DEVELOPER_DIR="/Applications/Xcode-$DOTNET_XCODE_VERSION.app/"