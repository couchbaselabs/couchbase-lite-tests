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
   ./jenkins/pipelines/main/latest_successful_build.sh c 4.0.0
   ```

3. Build and Run

   From this directory (`servers/c`), use the platform build script in the `scripts` directory to build and assemble the built artifacts.
   The build script requires CBL edition, version, build number, and dataset version. When specifying the build number = 0, the script 
   will download the public release CBL binary. The dataset versions available now are 3.2 and 4.0. The built artifacts including the 
   TestServer binary or application and the asset folder will be located at `build/out/bin` directory.

### macOS

```
./scripts/build_macos.sh enterprise 4.0.0 8 4.0
cd build/out/bin
./testserver
```

### linux

```
./scripts/build_linux.sh enterprise 4.0.0 8 4.0
cd build/out/bin
./testserver
```

### iOS

```
./scripts/build_ios.sh all enterprise 4.0.0 8 4.0
SHARED_DIR="../../jenkins/pipelines/shared"
"${SHARED_DIR}/ios_app.sh" start "$("${SHARED_DIR}/ios_device.sh")" build/out/bin/TestServer.app
```

Android and Windows instruction are in progress.

## Development

### Tools

* VSCode with C++/CMake plugin or Jetbrains CLion

### Prepare Dataset

The first step before starting to develop the project is to select and copy the dataset version
you want to use in your development. The current dataset vesions are 3.2 and 4.0. 

```
./scripts/prepare_env.sh 4.0
```
The powershell script version for Windows is `prepare_env.ps1`.

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

Open the project from this directory which has the CMakeLists.txt file using VSCode with C++/CMake plugin or CLion.

#### iOS

Go to `platforms/ios` directory and open `TestServer.xcodeproj` using XCode.

#### Android

Go to `platforms/android` directory and open `settings.gradle` using Android Studio.

### Build with CBL-C and LiteCore Source

This is for debugging purposes with CBL-C and LiteCore.

1. Clone couchbase-lite-c named cblite at c test server directory.

```
git clone https://github.com/couchbase/couchbase-lite-C.git cblite
git checkout <your branch>
cd cblite && git submodule update --init --recursive
```

2. Update CMakeLists.txt as follows:

```
 add_subdirectory(vendor)
+add_subdirectory(cblite)
 
-find_package(CouchbaseLite REQUIRED VERSION 3.2.1 PATHS lib/libcblite)
+#find_package(CouchbaseLite REQUIRED VERSION 3.2.1 PATHS lib/libcblite)
 
 if(APPLE)
     set(CMAKE_INSTALL_RPATH "@loader_path")
@@ -92,6 +94,7 @@ target_include_directories(
         src/support/ext
         src/support/ws
         ${civetweb_SOURCE_DIR}/include
+       ${CMAKE_BINARY_DIR}/cblite/generated_headers/public
 )
```