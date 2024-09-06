export DOTNET_ROOT=$HOME/.dotnet
export DOTNET_VERSION="8.0"

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

function banner() {
    echo
    echo ${GREEN}===== $1 =====${NORMAL}
    echo
}

banner "Preparing .NET $DOTNET_VERSION environment"

if [ ! -f ./dotnet-install.sh ]; then
	curl -LO https://dot.net/v1/dotnet-install.sh
	chmod +x ./dotnet-install.sh
fi

banner "Installing .NET $DOTNET_VERSION"

./dotnet-install.sh -c $DOTNET_VERSION

banner "Installing XHarness"

$HOME/.dotnet/dotnet tool install --global --add-source https://pkgs.dev.azure.com/dnceng/public/_packaging/dotnet-eng/nuget/v3/index.json Microsoft.DotNet.XHarness.CLI --version "8.0.0-prerelease*"

banner "Installing MAUI workload"

$HOME/.dotnet/dotnet workload install maui

banner "Copying dataset resources"

pushd $SCRIPT_DIR/../testserver/Resources/Raw
cp -f $SCRIPT_DIR/../../../dataset/server/dbs/*.zip .
cp -Rf $SCRIPT_DIR/../../../dataset/server/blobs .
popd