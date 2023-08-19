cmake_minimum_required(VERSION 3.11)
cmake_policy(VERSION 3.11)
cmake_policy(SET CMP0077 NEW)

set(CMAKE_OSX_DEPLOYMENT_TARGET "10.15")
set(CMAKE_OSX_ARCHITECTURES x86_64 arm64)

project(TestServer)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_INSTALL_PREFIX ${CMAKE_CURRENT_BINARY_DIR}/out)

add_subdirectory(vendor)

get_directory_property(civetweb_SOURCE_DIR DIRECTORY vendor DEFINITION civetweb_SOURCE_DIR)

message(STATUS ${CMAKE_LIBRARY_ARCHITECTURE})
find_package(CouchbaseLite 3.1.0 REQUIRED PATHS lib/libcblite)

if(APPLE)
    set(CMAKE_INSTALL_RPATH "@loader_path")
elseif(CMAKE_SYSTEM_NAME STREQUAL "Linux")
    set(CMAKE_INSTALL_RPATH "\$ORIGIN")
endif()

set(SOURCE_FILES
        src/main.cpp
        src/Dispatcher.cpp
        src/Request.cpp
        src/TestServer.cpp
        src/cbl/CBLManager.cpp
        src/cbl/CBLReplicationFilter.cpp
        src/cbl/CollectionSpec.cpp
        src/cbl/Fleece.cpp
        src/cbl/KeyPath.cpp
        src/cbl/Snapshot.cpp
        src/dispatcher/GetRoot.cpp
        src/dispatcher/PostGetAllDocuments.cpp
        src/dispatcher/PostGetDocument.cpp
        src/dispatcher/PostGetReplicatorStatus.cpp
        src/dispatcher/PostReset.cpp
        src/dispatcher/PostSnapshotDocuments.cpp
        src/dispatcher/PostStartReplicator.cpp
        src/dispatcher/PostUpdateDatabase.cpp
        src/dispatcher/PostVerifyDocuments.cpp
        src/support/Error.cpp
        src/support/Log.cpp
        src/support/StringUtil.cpp
        src/support/UUID.cpp
        src/support/ZipUtil.cpp)

add_executable(testserver ${SOURCE_FILES})

if(APPLE)
    target_sources(
            testserver PRIVATE
            src/support/Device+Apple.mm
            src/support/Files+Apple.mm
    )
else()
    target_sources(
            testserver PRIVATE
            src/support/Device.cpp
            src/support/Files.cpp
    )
endif()

target_link_libraries(
        testserver PRIVATE
        civetweb-c-library
        nlohmann_json::nlohmann_json
        cblite
        zip
)

target_include_directories(
        testserver PRIVATE
        src
        src/cbl
        src/dispatcher
        src/support
        src/support/ext
        ${civetweb_SOURCE_DIR}/include
)

target_compile_definitions(
        testserver PRIVATE
        -DJSON_USE_IMPLICIT_CONVERSIONS=0
        -DHAS_UNCAUGHT_EXCEPTIONS=1
)

if(MSVC)
    target_include_directories(
            testserver PRIVATE
            src/support/msvc
    )
    target_sources(
            testserver PRIVATE
            src/support/msvc/asprintf.c
            src/support/msvc/vasprintf-msvc.c
    )
    target_link_libraries(
            testserver PRIVATE
            zlibstatic
    )
endif()

file(COPY assets DESTINATION ${CMAKE_CURRENT_BINARY_DIR})

install(
        TARGETS testserver
        RUNTIME DESTINATION bin
)
