# Multiplatform CBL Testing

This directory contains scripts and configurations for running Couchbase Lite (CBL) tests across multiple platforms with platform-specific versions and topologies.

## Key Features

- **Platform-Specific Versioning**: Deploy different CBL versions to different platforms in a single test run
- **Auto-Fetch Latest Builds**: Automatically fetch the latest successful build numbers for each platform
- **Platform-Specific Setup**: Calls appropriate setup scripts for each platform (ADB for Android, env prep for .NET, etc.)
- **Dynamic Topology Composition**: Uses existing platform-specific topology files and composes them dynamically
- **Multi-OS Support**: Handles platforms with multiple OS variants (.NET, Java, C)
- **Supported Platforms**: iOS, Android, .NET, Java, C
- **Automated Setup**: Full environment setup and teardown with platform-specific requirements
- **Backward Compatibility**: Supports both auto-fetch and explicit build specifications

## Usage

### Command Line

#### Auto-Fetch Mode (Recommended)
```bash
./test_multiplatform.sh "ios:3.2.3 android:3.1.5 dotnet:3.2.0" 3.2 3.2.3
```

#### OS-Specific Mode
```bash
./test_multiplatform.sh "ios:3.2.3 dotnet:windows:3.2.0 c:linux:3.2.1" 3.2 3.2.3
```

#### Explicit Build Mode
```bash
./test_multiplatform.sh "ios:3.2.3-6 android:3.1.5-10 dotnet:3.2.0-8" 3.2 3.2.3
```

#### OS-Specific with Explicit Builds
```bash
./test_multiplatform.sh "dotnet:windows:3.2.0-8 c:linux:3.2.1-5" 3.2 3.2.3
```

### Parameters

1. **PLATFORM_VERSIONS**: Space-separated list of platform specifications
   - **Auto-fetch format**: `platform:version` (recommended)
   - **OS-specific format**: `platform:os:version` (for multi-OS platforms)
   - **Explicit format**: `platform:version-build`
   - **OS-specific explicit**: `platform:os:version-build`
   - **Examples**: 
     - Auto-fetch: `"ios:3.2.3 android:3.1.5"`
     - OS-specific: `"dotnet:windows:3.2.0 c:linux:3.2.1"`
     - Explicit: `"ios:3.2.3-6 android:3.1.5-10"`
     - OS-specific explicit: `"dotnet:windows:3.2.0-8 c:linux:3.2.1-5"`
   - **Supported platforms**: `ios`, `android`, `dotnet`, `java`, `c`
   - **Supported OS**: `windows`, `macos`, `linux`, `android`, `ios`

2. **CBL_DATASET_VERSION**: Dataset version to use (e.g., `3.2`)

3. **SGW_VERSION**: Sync Gateway version (e.g., `3.2.3`)

4. **TEST_NAME**: Optional test name to run (defaults to `test_delta_sync.py::TestDeltaSync::test_delta_sync_replication`)

**Note**: SSH private key is hardcoded to `~/.ssh/jborden.pem`

### Platform Mapping

The system automatically maps platform names in topology files to version specifications:

- `swift_ios`, `ios` → `ios` version
- `jak_android`, `java_android`, `dotnet_android` → `android` version  
- `dotnet_android`, `dotnet_windows`, `dotnet_macos` → `dotnet` version
- `java_windows`, `java_linux` → `java` version
- `c_linux`, `c_windows`, `c_macos` → `c` version

## Topology Configuration

### Dynamic Topology Composition

The system now uses **dynamic topology composition** from existing platform-specific topology files:

#### **Platform Topology Sources:**
- **iOS**: `jenkins/pipelines/QE/ios/topology_single_device.json`
- **Android**: `jenkins/pipelines/QE/android/topology_single_device.json`
- **.NET**: `jenkins/pipelines/QE/dotnet/topologies/topology_single_*.json`
- **Java**: `jenkins/pipelines/QE/java/topologies/topology_single_*.json`
- **C**: `jenkins/pipelines/QE/c/topologies/topology_single_*.json`

#### **Multi-OS Platform Support:**

For platforms supporting multiple operating systems:

| Platform | Available Topologies |
|----------|---------------------|
| **.NET** | `topology_single_windows.json`, `topology_single_macos.json`, `topology_single_android.json`, `topology_single_ios.json` |
| **C** | `topology_single_windows.json`, `topology_single_macos.json`, `topology_single_linux_x86_64.json`, `topology_single_android.json`, `topology_single_ios.json` |
| **Java** | Similar multi-OS support (TBD based on available files) |

#### **Smart Platform Selection:**

The system automatically:
- **Loads appropriate topology files** for each requested platform
- **Selects the first available topology** for multi-OS platforms (default behavior)
- **Composes a unified topology** with all requested test servers
- **Applies platform-specific versions** to each server
- **Handles different device locations** (localhost, device IDs, instance IDs)

## Examples

### iOS and Android Testing (Auto-Fetch)
```bash
# Automatically gets latest successful builds
./test_multiplatform.sh "ios:3.2.3 android:3.1.5" 3.2 3.2.3
```

### iOS and Android Testing (Explicit)
```bash
# Uses specific build numbers
./test_multiplatform.sh "ios:3.2.3-6 android:3.1.5-10" 3.2 3.2.3
```

### Full Platform Matrix (Auto-Fetch)
```bash
# Gets latest builds for all platforms
./test_multiplatform.sh "ios:3.2.3 android:3.1.5 dotnet:3.2.0 java:3.1.8 c:3.2.1" 3.2 3.2.3
```

### OS-Specific Platform Testing
```bash
# Specify exact OS variants for multi-OS platforms
./test_multiplatform.sh "ios:3.2.3 dotnet:windows:3.2.0 dotnet:macos:3.2.0 c:linux:3.2.1" 3.2 3.2.3
```

### Mixed Mode (Auto-Fetch + Explicit + OS-Specific)
```bash
# iOS auto-fetch, Android explicit build, .NET Windows-specific
./test_multiplatform.sh "ios:3.2.3 android:3.1.5-10 dotnet:windows:3.2.0" 3.2 3.2.3
```

### Single Platform Testing
```bash
# Single platform with auto-fetch
./test_multiplatform.sh "ios:3.2.3" 3.2 3.2.3
```

### Using Custom Test
```bash
# Specify custom test to run
./test_multiplatform.sh "ios:3.2.3-6 android:3.1.5-10" 3.2 3.2.3 "test_no_conflicts.py::TestNoConflicts::test_multiple_cbls_updates_concurrently_with_push"
```

## Jenkins Integration

Use the provided `Jenkinsfile` for automated CI/CD integration:

1. **Platform Versions Parameter**: Input platform specifications
2. **Auto-Fetch Toggle**: Enable/disable automatic build fetching
3. **Automatic Validation**: Parameter validation and error handling
4. **Cleanup**: Automatic teardown after test completion

## Auto-Fetch Latest Builds

The system automatically fetches the latest successful build numbers using the Couchbase build API:

- **Endpoint**: `http://proget.build.couchbase.com:8080/api/get_version`
- **Parameters**: `product=couchbase-lite-{platform}&version={version}&ee=true`
- **Error Handling**: Fails if API call fails - no fallback behavior
- **Benefits**: Always uses the most recent healthy builds without manual tracking

### Manual Build Lookup

Use the standalone script to check available builds:

```bash
# Check latest build for iOS 3.2.3
./latest_successful_build.sh ios 3.2.3

# Check latest build for Android 3.1.5  
./latest_successful_build.sh android 3.1.5
```

## File Structure

```
multiplatform/
├── test_multiplatform.sh           # Main test execution script
├── setup_multiplatform.py          # Platform-specific setup logic with dynamic topology composition
├── latest_successful_build.sh      # Standalone build lookup utility
├── config_multiplatform.json       # Configuration file
├── teardown.sh                     # Cleanup script
├── Jenkinsfile                      # Jenkins pipeline
└── README.md                        # This file
```

## Platform-Specific Notes

### iOS (`swift_ios`)
- Requires physical device connection
- Uses device UDID for targeting
- Supports iOS SDK versions
- **Topology**: Single device topology from QE/ios directory

### Android (`jak_android`, `java_android`, `dotnet_android`)
- Supports both Java and .NET implementations
- Uses device serial numbers
- Requires ADB connectivity
- **Topology**: Single device topology from QE/android directory

### .NET (`dotnet_windows`, `dotnet_macos`, `dotnet_android`, `dotnet_ios`)
- Cross-platform .NET support
- Multiple OS targets with separate topologies
- Framework-specific builds
- **Topologies**: Platform-specific files in QE/dotnet/topologies/

### Java (`java_windows`, `java_linux`)
- Pure Java implementations
- Linux and Windows support
- JVM compatibility testing
- **Topologies**: Platform-specific files in QE/java/topologies/

### C (`c_linux_x86_64`, `c_windows`, `c_macos`)
- Native C implementations
- Multi-OS support with architecture variants
- Compiler-specific builds
- **Topologies**: Platform-specific files in QE/c/topologies/

## Troubleshooting

### Common Issues

1. **Invalid Platform Specification**: Ensure format is `platform:version[-build]`
2. **Missing Private Key**: Verify SSH key path and permissions
3. **Platform Not Found**: Check platform name mapping in setup script
4. **Version Resolution**: Ensure specified versions exist in build system
5. **Missing Topology Files**: Verify platform-specific topology files exist in QE directories

### Debug Mode

Set environment variable for verbose output:
```bash
export DEBUG=1
./test_multiplatform.sh "ios:3.2.3" 3.2 3.2.3
```

## Contributing

When adding new platforms:

1. Add platform detection logic in `setup_multiplatform.py`
2. Add topology file discovery logic for the platform
3. Create appropriate topology examples in the platform's QE directory
4. Update this README with platform-specific notes
5. Test with actual device configurations 