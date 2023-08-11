#!/bin/sh

#  GetCBLVersion.sh
#  CBL-Tests-iOS
#
#  Created by Callum Birks on 11/08/2023.
#

# Install jq (JSON parser) if it isn't installed
if ! command -v /opt/homebrew/bin/jq &> /dev/null; then
    /opt/homebrew/bin/brew install jq
fi

# Path to Package.resolved (Where Swift Package Manager keeps info about package dependencies)
PACKAGE_RESOLVED_FILE="$SRCROOT/CBL-Tests-iOS.xcodeproj/project.xcworkspace/xcshareddata/swiftpm/Package.resolved"

# Extract the version using jq
PACKAGE_VERSION=$(/opt/homebrew/bin/jq -r '.pins[] | select(.identity == "couchbase-lite-swift-ee") | .state.version' "$PACKAGE_RESOLVED_FILE")

# Path to the Swift file that will be generated
OUTPUT_FILE="$SRCROOT/PackageVersion.swift"

# Create the directory if it doesn't exist
mkdir -p "$(dirname "$OUTPUT_FILE")"

# Delete existing file
rm $OUTPUT_FILE

# Write the Swift file
echo "struct PackageVersion {" > $OUTPUT_FILE
echo "    static let version = \"$PACKAGE_VERSION\"" >> $OUTPUT_FILE
echo "}" >> $OUTPUT_FILE
