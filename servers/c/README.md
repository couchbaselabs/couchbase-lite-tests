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
   ./jenkins/pipelines/main/latest_successful_build.sh c 3.2.0
   ```

3. Build and Run

   From this directory (`servers/c`), use the platform build script in the `scripts` directory to build and assemble the built artifacts.
   The build script requires CBL version number and optional build number. Without specifying the build number, the script will download
   the public release CBL binary. The built artifacts including the TestServer binary or application and the asset folder will be located at
   `build/out/bin` directory.

### macOS

```
./scripts/build_macos.sh enterprise 3.2.0 28
cd build/out/bin
./testserver
```

### linux

```
./scripts/build_linux.sh enterprise 3.2.0 28
cd build/out/bin
./testserver
```

### iOS

```
./scripts/build_ios.sh all enterprise 3.2.0 28
cd build/out/bin
ios kill com.couchbase.CBLTestServer
ios install --path=TestServer.app
ios launch com.couchbase.CBLTestServer
```

* The above uses [go-ios](https://github.com/danielpaulus/go-ios) to install and run the TestServer app. 
* go-ios doesn't support XCode 15 and iOS 17 at the moment. For XCode 15 and iOS 17, use xcrun command.
  
  ```
  xcrun devicectl device install app --device <device uuid|ecid|udid|name> ./TestServer.app
  xcrun devicectl device process launch --device <device uuid|ecid|udid|name> com.couchbase.CBLTestServer
  ```
  
* To run on the test server on the device, use xcrun simctl command.
  ```
  xcrun simctl install booted ./TestServer.app
  ```

Android and Windows instruction are in progress.

## Development

### Tools

* VSCode with C++/CMake plugin or Jetbrains CLion

### Download Couchbase Lite

The first step before starting to develop the project is to download CBL library.

#### macOS, iOS, Android, Linux

```
./scripts/download_cbl.sh macos enterprise 3.1.1
```

#### Windows

```
.\scripts\download_cbl.ps1 enterprise 3.1.1
```

### Development Projects

#### CMake for macOS, Linux, and Windows

Open the project from this directory which has the CMakeLists.txt file using VSCode with C++/CMake plugin or CLion.

#### iOS

Go to `platforms/ios` directory and open `TestServer.xcodeproj` using XCode.

#### Android

Go to `platforms/android` directory and open `settings.gradle` using Android Studio.
