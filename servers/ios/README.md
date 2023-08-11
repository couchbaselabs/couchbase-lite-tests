#  couchbase-lite-tests iOS Server

If you're having trouble with SPM fetching dependencies, try adding your GitHub account to Xcode, and set "Clone Using" to HTTPS.
Not sure if that's still necessary, but I had troubles at first.

Currently, will receive a couple thread warnings on App run, this is due to [an issue with Apple's swift-nio](https://github.com/apple/swift-nio/issues/2223)

All dependencies are managed via Swift PM (including CBL), so nothing manual is required.

The build process runs the `GetCBLVersion.sh` script to parse CBL version from Swift Package Manager's `Package.resolved`. This will require `brew` to be installed. (Or you can just temporarily remove the script from the Build Phases).
