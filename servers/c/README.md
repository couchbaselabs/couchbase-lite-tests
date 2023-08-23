## Supported Platforms

* macOS
* Linux
* Windows
* iOS
* Android 

## Requirements

* CMake 3.23+
* iOS : XCode 14.3+
* Android : Java 17+ and Android Studio 2022.2.1+
* Windows : Visual Studio 2017+

## Build

From this directory, use the build script for the platform in the `scripts` directory to build and assemble the 
built artifacts. The built artifacts including the TestServer binary or application and the asset folder 
for non-app platforms (macOs, linux, and Windows) will be located at `build/out/bin` directory. 

See the samples below for the usage of the build scripts.

### macOS

```
./scripts/build_macos.sh enterprise 3.1.1
```

### linux

```
./scripts/build_linux.sh enterprise 3.1.1
```

### Windows

```
.\scripts\build_wins.ps1 enterprise 3.1.1
```

### iOS

```
./scripts/build_ios.sh all enterprise 3.1.1
```

### Android

```
./scripts/build_android.sh all enterprise 3.1.1
```

## Development

### Preparation

The first step before starting to develop the project is to download CBL library and copy all required
assets (dataset files and SSL certificates) in place. To do that, use the prepare script as the 
samples below.

#### macOS, iOS, Android, Linux

```
./scripts/dev_prepare.sh macos enterprise 3.1.1
```

#### Windows

```
./scripts\dev_prepare.ps1 enterprise 3.1.1
```

### Development Projects

#### CMake for macOS, Linux, and Windows

Open the project from this directory which has the CMakeLists.txt file.

#### iOS

Go to `platforms/ios` directory and open `TestServer.xcodeproj` using XCode.

#### Android

Go to `platforms/android` directory and open `settings.gradle` using Android Studio.
