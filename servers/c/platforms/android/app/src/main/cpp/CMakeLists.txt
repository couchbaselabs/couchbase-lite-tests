
# For more information about using CMake with Android Studio, read the
# documentation: https://d.android.com/studio/projects/add-native-code.html

# Sets the minimum version of CMake required to build the native library.

cmake_minimum_required(VERSION 3.22.1)

project("testserver")

set(CMAKE_CXX_STANDARD 17)

if(CMAKE_HOST_SYSTEM_NAME STREQUAL "Windows")
    # Windows cannot handle the symlinks that are present here
    set(SHARED_SYMLINK "${CMAKE_CURRENT_SOURCE_DIR}/shared")
    set(VENDOR_SYMLINK "${CMAKE_CURRENT_SOURCE_DIR}/vendor")
    set(SHARED_SRC "${CMAKE_CURRENT_SOURCE_DIR}/../../../../../../src")
    set(VENDOR_SRC "${CMAKE_CURRENT_SOURCE_DIR}/../../../../../../vendor")

    if(EXISTS ${SHARED_SYMLINK})
        if(NOT IS_DIRECTORY ${SHARED_SYMLINK})
            file(REMOVE ${SHARED_SYMLINK})
            file(COPY ${SHARED_SRC} DESTINATION ${CMAKE_CURRENT_SOURCE_DIR})
            file(RENAME "${CMAKE_CURRENT_SOURCE_DIR}/src" "shared")
        endif()
    endif()

    if(EXISTS ${VENDOR_SYMLINK})
        if(NOT IS_DIRECTORY ${VENDOR_SYMLINK})
            file(REMOVE ${VENDOR_SYMLINK})
            file(COPY ${VENDOR_SRC} DESTINATION ${CMAKE_CURRENT_SOURCE_DIR})
        endif()
    endif()
endif()

set(SHARED_SRC_DIR ${PROJECT_SOURCE_DIR}/shared)
set(SHARED_SRC
        ${SHARED_SRC_DIR}/Dispatcher.cpp
        ${SHARED_SRC_DIR}/Request.cpp
        ${SHARED_SRC_DIR}/SessionManager.cpp
        ${SHARED_SRC_DIR}/TestServer.cpp
        ${SHARED_SRC_DIR}/cbl/CBLManager.cpp
        ${SHARED_SRC_DIR}/cbl/CBLReplicationConflictResolver.cpp
        ${SHARED_SRC_DIR}/cbl/CBLReplicationFilter.cpp
        ${SHARED_SRC_DIR}/cbl/CollectionSpec.cpp
        ${SHARED_SRC_DIR}/cbl/Fleece.cpp
        ${SHARED_SRC_DIR}/cbl/KeyPath.cpp
        ${SHARED_SRC_DIR}/cbl/Snapshot.cpp
        ${SHARED_SRC_DIR}/dispatcher/GetRoot.cpp
        ${SHARED_SRC_DIR}/dispatcher/PostGetAllDocuments.cpp
        ${SHARED_SRC_DIR}/dispatcher/PostGetDocument.cpp
        ${SHARED_SRC_DIR}/dispatcher/PostGetReplicatorStatus.cpp
        ${SHARED_SRC_DIR}/dispatcher/PostNewSession.cpp
        ${SHARED_SRC_DIR}/dispatcher/PostPerformMaintenance.cpp
        ${SHARED_SRC_DIR}/dispatcher/PostReset.cpp
        ${SHARED_SRC_DIR}/dispatcher/PostRunQuery.cpp
        ${SHARED_SRC_DIR}/dispatcher/PostSnapshotDocuments.cpp
        ${SHARED_SRC_DIR}/dispatcher/PostStartListener.cpp
        ${SHARED_SRC_DIR}/dispatcher/PostStopListener.cpp
        ${SHARED_SRC_DIR}/dispatcher/PostStartReplicator.cpp
        ${SHARED_SRC_DIR}/dispatcher/PostStopReplicator.cpp
        ${SHARED_SRC_DIR}/dispatcher/PostUpdateDatabase.cpp
        ${SHARED_SRC_DIR}/dispatcher/PostVerifyDocuments.cpp
        ${SHARED_SRC_DIR}/log/Log.cpp
        ${SHARED_SRC_DIR}/log/RemoteLogger.cpp
        ${SHARED_SRC_DIR}/support/Android.cpp
        ${SHARED_SRC_DIR}/support/Device.cpp
        ${SHARED_SRC_DIR}/support/FileDownloader.cpp
        ${SHARED_SRC_DIR}/support/Error.cpp
        ${SHARED_SRC_DIR}/support/Files.cpp
        ${SHARED_SRC_DIR}/support/StringUtil.cpp
        ${SHARED_SRC_DIR}/support/UUID.cpp
        ${SHARED_SRC_DIR}/support/ZipUtil.cpp)

set(LIB_SRC
        ${SHARED_SRC}
        JNIUtil.cpp
        testserver.cpp)

# Creates and names a library, sets it as either STATIC
# or SHARED, and provides the relative paths to its source code.
# You can define multiple libraries, and CMake builds them for you.
# Gradle automatically packages shared libraries with your APK.

add_library(testserver SHARED ${LIB_SRC})

#if(NOT DEFINED CBL_VERSION)
#    message(FATAL_ERROR "Please set CBL_VERSION to the version of Couchbase Lite you are using.")
#endif()

set(CMAKE_FIND_ROOT_PATH_MODE_PACKAGE NEVER)
#find_package(CouchbaseLite ${CBL_VERSION} REQUIRED PATHS ${PROJECT_SOURCE_DIR}/lib/libcblite-${CBL_VERSION})

find_package(CouchbaseLite 3.2.1 REQUIRED PATHS ${PROJECT_SOURCE_DIR}/lib/libcblite-3.2.1)

set(CMAKE_FIND_ROOT_PATH_MODE_PACKAGE ONLY)

add_subdirectory(vendor)
get_directory_property(civetweb_SOURCE_DIR DIRECTORY vendor DEFINITION civetweb_SOURCE_DIR)

find_library(log-lib log)

target_link_libraries(testserver
        ${log-lib}
        civetweb-c-library
        nlohmann_json::nlohmann_json
        cblite
        zip
        ixwebsocket)

target_include_directories(
        testserver PRIVATE
        ${CMAKE_CURRENT_SOURCE_DIR}
        ${SHARED_SRC_DIR}
        ${SHARED_SRC_DIR}/cbl
        ${SHARED_SRC_DIR}/dispatcher
        ${SHARED_SRC_DIR}/log
        ${SHARED_SRC_DIR}/support
        ${SHARED_SRC_DIR}/support/ext
        ${civetweb_SOURCE_DIR}/include)

target_compile_definitions(
        testserver PRIVATE
        -DJSON_USE_IMPLICIT_CONVERSIONS=0
        -DHAS_UNCAUGHT_EXCEPTIONS=1)