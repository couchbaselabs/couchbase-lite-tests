## Supported Platforms

* macOS
* Linux
* Windows
* iOS
* Android 

## Requirements

* CMake 3.23+
* Apple : XCode 14.3+
* Android : Java 17+ and Android Studio 2022.2.1+
* Windows : Visual Studio 2017+

## Build and Run Test Server

1. Login to Couchbase VPN. This is required to download CBL binary built by the CI system.

2. Find you the latest successful build number. Skip this if you have already known a specific build to test.

   ```
   ./jenkins/pipelines/dev_e2e/main/latest_successful_build.sh c 4.0.0
   ```

3. Build and Run

   From this directory (`servers/c`), use the platform build script in the `scripts` directory to build and assemble the built artifacts.
   The build script requires CBL version and build number. When specifying the build number = 0, the script 
   will download the public release CBL binary. The built artifacts will be located at `build/out/bin` directory.

### macOS

```
./scripts/build_macos.sh 4.0.0 43
cd build/out/bin
./testserver
```

### linux

```
./scripts/build_linux.sh 4.0.0 43
cd build/out/bin
./testserver
```

### iOS

```
./scripts/build_ios.sh all 4.0.0 43
SHARED_DIR="../../jenkins/pipelines/shared"
"${SHARED_DIR}/ios_app.sh" start "$("${SHARED_DIR}/ios_device.sh")" build/out/bin/TestServer.app
```

Android and Windows instruction are in progress.

## Development

### Tools

* Jetbrains CLion or VSCode with C++/CMake plugin

### Download Couchbase Lite

The next step is to download CBL library.

#### macOS, iOS, Android, Linux

```
./scripts/download_cbl.sh macos enterprise 4.0.0
```

#### Windows

```
.\scripts\download_cbl.ps1 enterprise 4.0.0
```

### Development Projects

#### CMake for macOS, Linux, and Windows

Open the project from this directory which has the CMakeLists.txt file using CLion (Recommended) or VSCode with C++/CMake plugin.

#### CLion

1. Open the c test server directory with CLion.

2. When configurating CMake, add `DCBL_VERSION=<CBL Version>` option with the CBL version you are using. 
    If using CLion, add the option to Settings > Build, Execution, Deploymenet > CMake > CMake Options

3. CLion will load the CMake Project and create `cmake-build-debug` directory for building.

4. If you switch CBL version, ensure to clean `cmake-build-debug` the directory either by removing the directory 
    or find an option to clean it from the CLion.

#### iOS

Go to `platforms/ios` directory and open `TestServer.xcodeproj` using XCode.

#### Android

Go to `platforms/android` directory and open `settings.gradle` using Android Studio.

### Build with CBL-C and LiteCore Source

This is for debugging purposes with CBL-C and LiteCore.

1. Clone couchbase-lite-C as couchbase-lite-c at c test server directory.

```
git clone --recurse-submodules https://github.com/couchbase/couchbase-lite-C.git couchbase-lite-c
```

2. Clone couchbase-lite-c-ee at c test server directory.

```
git clone --recurse-submodules https://github.com/couchbase/couchbase-lite-c-ee.git
```

3. Create symlink for LiteCore EE

```
pushd couchbase-lite-c/vendor
ln -s ../../couchbase-lite-c-ee/couchbase-lite-core-EE couchbase-lite-core-EE
popd
```

4. When configurating CMake, add `-DCBL_FROM_SOURCE=ON`.
    If using CLion, add the option to Settings > Build, Execution, Deploymenet > CMake > CMake Options

```
mkdir build & cd build
cmake -DCBL_FROM_SOURCE=ON  ..
make
```