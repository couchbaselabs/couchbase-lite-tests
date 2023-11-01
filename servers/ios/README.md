#  iOS TestServer

Before building the project, download and copy `CouchbaseLiteSwift.xcframework` into the `Frameworks` directory.

The build process runs the scripts/`gen_cbl_version.sh` script to parse CBL version from CouchbaseLiteSwift.framework's Info.plist file.

Currently, will receive a couple thread warnings on App run, this is due to [an issue with Apple's swift-nio](https://github.com/apple/swift-nio/issues/2223)
