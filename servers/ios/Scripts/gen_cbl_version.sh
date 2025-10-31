#!/bin/bash -e

# Path to CouchbaseLiteSwift.xcframework
CBL_XC_FRAMEWORK=$1      
CBL_VERSION_OUTPUT_FILE=$2

# Path to the framework that Xcode is currently linking
CBL_INFO_PLIST_FILE="${CBL_XC_FRAMEWORK}/ios-arm64/CouchbaseLiteSwift.framework/Info.plist"

if [ ! -f "${CBL_INFO_PLIST_FILE}" ]; then
    echo "Error - Info.plist not found at ${CBL_INFO_PLIST_FILE}"
    exit 1
fi

CBL_VERSION=$(/usr/libexec/PlistBuddy -c "Print :CFBundleShortVersionString" "${CBL_INFO_PLIST_FILE}")
CBL_BUILD=$(/usr/libexec/PlistBuddy -c "Print :CFBundleVersion" "${CBL_INFO_PLIST_FILE}")

# Gen CBLVersion.swift
cat <<EOF > "${CBL_VERSION_OUTPUT_FILE}"
struct CBLVersion {
    static let version = "${CBL_VERSION}"
    static let build = "${CBL_BUILD}"
}
EOF
