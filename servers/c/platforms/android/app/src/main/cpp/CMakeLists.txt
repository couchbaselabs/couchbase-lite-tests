
# For more information about using CMake with Android Studio, read the
# documentation: https://d.android.com/studio/projects/add-native-code.html

# Sets the minimum version of CMake required to build the native library.

cmake_minimum_required(VERSION 3.22.1)

project("testserver")

set(CMAKE_CXX_STANDARD 17)

set(SHARED_SRC_DIR ${PROJECT_SOURCE_DIR}/shared)
set(SHARED_SRC
        ${SHARED_SRC_DIR}/Dispatcher.cpp
        ${SHARED_SRC_DIR}/Request.cpp
        ${SHARED_SRC_DIR}/TestServer.cpp
        ${SHARED_SRC_DIR}/cbl/CBLManager.cpp
        ${SHARED_SRC_DIR}/cbl/CBLReplicationFilter.cpp
        ${SHARED_SRC_DIR}/cbl/CollectionSpec.cpp
        ${SHARED_SRC_DIR}/cbl/Fleece.cpp
        ${SHARED_SRC_DIR}/cbl/KeyPath.cpp
        ${SHARED_SRC_DIR}/cbl/Snapshot.cpp
        ${SHARED_SRC_DIR}/dispatcher/GetRoot.cpp
        ${SHARED_SRC_DIR}/dispatcher/PostGetAllDocuments.cpp
        ${SHARED_SRC_DIR}/dispatcher/PostGetDocument.cpp
        ${SHARED_SRC_DIR}/dispatcher/PostPerformMaintenance.cpp
        ${SHARED_SRC_DIR}/dispatcher/PostGetReplicatorStatus.cpp
        ${SHARED_SRC_DIR}/dispatcher/PostReset.cpp
        ${SHARED_SRC_DIR}/dispatcher/PostRunQuery.cpp
        ${SHARED_SRC_DIR}/dispatcher/PostSnapshotDocuments.cpp
        ${SHARED_SRC_DIR}/dispatcher/PostStartReplicator.cpp
        ${SHARED_SRC_DIR}/dispatcher/PostUpdateDatabase.cpp
        ${SHARED_SRC_DIR}/dispatcher/PostVerifyDocuments.cpp
        ${SHARED_SRC_DIR}/support/Android.cpp
        ${SHARED_SRC_DIR}/support/Device.cpp
        ${SHARED_SRC_DIR}/support/Error.cpp
        ${SHARED_SRC_DIR}/support/Files.cpp
        ${SHARED_SRC_DIR}/support/Log.cpp
        ${SHARED_SRC_DIR}/support/StringUtil.cpp
        ${SHARED_SRC_DIR}/support/UUID.cpp
        ${SHARED_SRC_DIR}/support/ZipUtil.cpp)

set(LIB_SRC
        ${SHARED_SRC}
        testserver.cpp)

# Creates and names a library, sets it as either STATIC
# or SHARED, and provides the relative paths to its source code.
# You can define multiple libraries, and CMake builds them for you.
# Gradle automatically packages shared libraries with your APK.

add_library(testserver SHARED ${LIB_SRC})

set(CMAKE_FIND_ROOT_PATH_MODE_PACKAGE NEVER)
find_package(CouchbaseLite 3.1.0 REQUIRED PATHS ${PROJECT_SOURCE_DIR}/lib/libcblite)
set(CMAKE_FIND_ROOT_PATH_MODE_PACKAGE ONLY)

add_subdirectory(vendor)
get_directory_property(civetweb_SOURCE_DIR DIRECTORY vendor DEFINITION civetweb_SOURCE_DIR)

find_library(log-lib log)

target_link_libraries(testserver
        ${log-lib}
        civetweb-c-library
        nlohmann_json::nlohmann_json
        cblite
        zip)

target_include_directories(
        testserver PRIVATE
        ${SHARED_SRC_DIR}
        ${SHARED_SRC_DIR}/cbl
        ${SHARED_SRC_DIR}/dispatcher
        ${SHARED_SRC_DIR}/support
        ${SHARED_SRC_DIR}/support/ext
        ${civetweb_SOURCE_DIR}/include)

target_compile_definitions(
        testserver PRIVATE
        -DJSON_USE_IMPLICIT_CONVERSIONS=0
        -DHAS_UNCAUGHT_EXCEPTIONS=1)