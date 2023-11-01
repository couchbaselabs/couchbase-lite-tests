#!/bin/bash -e

# Frameworks/CouchbaseLiteSwift.xcframework
CBL_XC_FRAMEWORK=$1
# TestServer/CBLVersion.swift"
CBL_VERSION_OUTPUT_FILE=$2

CBL_INFO_PLIST_FILE="${CBL_XC_FRAMEWORK}/ios-arm64/CouchbaseLiteSwift.framework/Info.plist"
CBL_VERSION=`defaults read ${CBL_INFO_PLIST_FILE} CFBundleShortVersionString`
CBL_BUILD=`defaults read ${CBL_INFO_PLIST_FILE} CFBundleVersion`

# Delete existing CBLVersion.swift
rm -f "${CBL_VERSION_OUTPUT_FILE}"

# Write a new CBLVersion.swift
echo "struct CBLVersion {" > "${CBL_VERSION_OUTPUT_FILE}"
echo "    static let version = \"${CBL_VERSION}\"" >> "${CBL_VERSION_OUTPUT_FILE}"
echo "    static let build = \"${CBL_BUILD}\"" >> "${CBL_VERSION_OUTPUT_FILE}"
echo "}" >> "${CBL_VERSION_OUTPUT_FILE}"
