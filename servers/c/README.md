### Supported Platforms

* macOS
* Linux
* Windows
* iOS
* Android 

### Requirements

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
assets (dataset files and SSL certificates) in place. To do that, you can use the prepare script
depending on the platform you are working on. See the samples below.

Note: This step will be run only once unless there is a change
to the dataset or you want to use a different CBL library or you want to work on a different platform.

#### Non-Windows (macOS, iOS, Android, Linux)

Run `scripts/dev_prepare.sh` and specify the platform (macos | linux | ios | android), CBL edition, CBL version,
and the optional CBL build number.

```
scripts/dev_prepare.sh macos enterprise 3.1.1
```

Note: For iOS project, the prepare script will also run cmake command to download all other dependencies specified in
`vendor/CMakeLists.txt`. 

#### Windows

Run `scripts\dev_prepare.ps1` and specify CBL edition, CBL version, and the optional CBL build number.

```
scripts\dev_prepare.ps1 enterprise 3.1.1
```

### Development Projects

#### CMake (macOS, Linux, and Windows)

Open the project from the current c server directory that has CMakeLists.txt file.

#### iOS

Go to `platforms/ios` directory and open `TestServer.xcodeproj` using XCode.

#### Android

Go to `platforms/android` directory and open `settings.gradle` using Android Studio.
