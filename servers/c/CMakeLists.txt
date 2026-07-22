cmake_minimum_required(VERSION 3.11)
cmake_policy(VERSION 3.11)
cmake_policy(SET CMP0077 NEW)

option(CBL_FROM_SOURCE "Build against couchbase-lite-c source in this repo" OFF)

set(CMAKE_OSX_DEPLOYMENT_TARGET "10.15")
set(CMAKE_OSX_ARCHITECTURES x86_64 arm64)

project(TestServer)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_INSTALL_PREFIX ${CMAKE_CURRENT_BINARY_DIR}/out)

add_subdirectory(vendor)

if(CBL_FROM_SOURCE)
    message(STATUS "BUILD_WITH_CBL_C_SRC=ON -> Building with couchbase-lite-c from source")
    # Add couchbase-lite-c subdirectory
    if(EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/couchbase-lite-c/CMakeLists.txt")
        set(BUILD_ENTERPRISE ON CACHE INTERNAL "Enterprise build enabled when using source" FORCE)
        add_subdirectory(couchbase-lite-c)
    else()
        message(FATAL_ERROR
                "BUILD_WITH_CBL_C_SRC=ON but couchbase-lite-c source directory not found at "
                "${CMAKE_CURRENT_SOURCE_DIR}/couchbase-lite-c")
    endif()
else()
    if(NOT DEFINED CBL_VERSION)
        message(FATAL_ERROR "Please pass -DCBL_VERSION to indicate which version of Couchbase Lite you will use")
    endif()

    # find_package(CouchbaseLite) only searches the lib/<triplet>/cmake multiarch
    # subdirectory shipped in the CBL tarball when CMAKE_LIBRARY_ARCHITECTURE is a
    # real GNU triple, which CMake only auto-detects on Debian-based distros. When
    # it doesn't, ask the C compiler for its target triple and rebuild it in the
    # Debian convention the CBL tarball uses (e.g. Arch's gcc reports
    # x86_64-pc-linux-gnu, but the tarball ships lib/x86_64-linux-gnu).
    if(CMAKE_SYSTEM_NAME STREQUAL "Linux" AND NOT CMAKE_LIBRARY_ARCHITECTURE MATCHES "^[^-]+-[^-]+-[^-]+")
        execute_process(
                COMMAND ${CMAKE_C_COMPILER} -dumpmachine
                OUTPUT_VARIABLE CMAKE_C_COMPILER_TARGET_TRIPLE
                OUTPUT_STRIP_TRAILING_WHITESPACE
        )
        string(REGEX REPLACE "^([^-]+)-.*" "\\1" CBL_COMPILER_CPU "${CMAKE_C_COMPILER_TARGET_TRIPLE}")
        set(CMAKE_LIBRARY_ARCHITECTURE "${CBL_COMPILER_CPU}-linux-gnu")
    endif()

    find_package(
            CouchbaseLite
            REQUIRED
            VERSION EXACT ${CBL_VERSION}
            PATHS lib/libcblite-${CBL_VERSION} lib/libcblite
            NO_DEFAULT_PATH
    )
    set(CBL_FROM_SOURCE OFF)
endif()

get_directory_property(civetweb_SOURCE_DIR DIRECTORY vendor DEFINITION civetweb_SOURCE_DIR)

if(APPLE)
    set(CMAKE_INSTALL_RPATH "@loader_path")
elseif(CMAKE_SYSTEM_NAME STREQUAL "Linux")
    set(CMAKE_INSTALL_RPATH "\$ORIGIN")
endif()

set(SOURCE_FILES
        src/main.cpp
        src/Dispatcher.cpp
        src/Request.cpp
        src/SessionManager.cpp
        src/TestServer.cpp
        src/cbl/CBLManager.cpp
        src/cbl/CBLReplicationConflictResolver.cpp
        src/cbl/CBLReplicationFilter.cpp
        src/cbl/CollectionSpec.cpp
        src/cbl/Fleece.cpp
        src/cbl/KeyPath.cpp
        src/cbl/Snapshot.cpp
        src/dispatcher/GetRoot.cpp
        src/dispatcher/PostGetAllDocuments.cpp
        src/dispatcher/PostGetDocument.cpp
        src/dispatcher/PostGetReplicatorStatus.cpp
        src/dispatcher/PostNewSession.cpp
        src/dispatcher/PostPerformMaintenance.cpp
        src/dispatcher/PostReset.cpp
        src/dispatcher/PostRunQuery.cpp
        src/dispatcher/PostSnapshotDocuments.cpp
        src/dispatcher/PostStartListener.cpp
        src/dispatcher/PostStartReplicator.cpp
        src/dispatcher/PostStopListener.cpp
        src/dispatcher/PostStopReplicator.cpp
        src/dispatcher/PostUpdateDatabase.cpp
        src/dispatcher/PostVerifyDocuments.cpp
        src/log/Log.cpp
        src/log/RemoteLogger.cpp
        src/support/Error.cpp
        src/support/StringUtil.cpp
        src/support/UUID.cpp
        src/support/ZipUtil.cpp
)

add_executable(testserver ${SOURCE_FILES})

if(APPLE)
    target_sources(
            testserver PRIVATE
            src/support/Device+Apple.mm
            src/support/Files+Apple.mm
            src/support/FileDownloader+Apple.mm
    )
else()
    target_sources(
            testserver PRIVATE
            src/support/Device.cpp
            src/support/Files.cpp
            src/support/FileDownloader.cpp
    )
endif()

target_link_libraries(
        testserver PRIVATE
        civetweb-c-library
        nlohmann_json::nlohmann_json
        cblite
        zip
        ixwebsocket
)

if(CMAKE_SYSTEM_NAME STREQUAL "Linux")
    # For FileDownloader on linux platform
    find_package(OpenSSL REQUIRED)
    target_link_libraries(
            testserver PRIVATE
            OpenSSL::SSL
            OpenSSL::Crypto)
endif()

target_include_directories(
        testserver PRIVATE
        src
        src/cbl
        src/dispatcher
        src/log
        src/support
        src/support/ext
        src/support/ws
        ${civetweb_SOURCE_DIR}/include
)


# If building from CBL's source, also include generated public headers
if(CBL_FROM_SOURCE)
    target_include_directories(
            testserver PRIVATE
            ${CMAKE_BINARY_DIR}/couchbase-lite-c/generated_headers/public
    )
endif()

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

install(
        TARGETS testserver
        RUNTIME DESTINATION bin
)

# Install CBL runtime artifacts when using prebuilt package
if(NOT CBL_FROM_SOURCE)
    get_target_property(CBLITE_DLL_LOCATION cblite IMPORTED_LOCATION_MINSIZEREL)
    get_filename_component(CBLITE_PARENT_DIR "${CBLITE_DLL_LOCATION}" DIRECTORY)
    file(GLOB CBLITE_FILES "${CBLITE_PARENT_DIR}/*cblite*")
    install(
            FILES ${CBLITE_FILES}
            DESTINATION ${CMAKE_INSTALL_PREFIX}/bin
    )
endif()