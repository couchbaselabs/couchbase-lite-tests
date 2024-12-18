#  iOS TestServer

## Build Steps

1. The first step before starting to develop the project is to select and copy the dataset version you want to use in your development. The current dataset vesions are 3.2 and 4.0. 

```
./Scripts/prepare_env.sh 4.0
```

2. Download and copy `CouchbaseLiteSwift.xcframework` into the `Frameworks` directory.

3. Open the `TestServer.xcodeproj` project using XCode and build.

The build process runs the scripts/`gen_cbl_version.sh` script to parse CBL version from CouchbaseLiteSwift.framework's Info.plist file.

Currently, will receive a couple thread warnings on App run, this is due to [an issue with Apple's swift-nio](https://github.com/apple/swift-nio/issues/2223)
