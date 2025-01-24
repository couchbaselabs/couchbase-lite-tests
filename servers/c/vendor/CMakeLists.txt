cmake_minimum_required(VERSION 3.11)
cmake_policy(VERSION 3.11)
cmake_policy(SET CMP0077 NEW)

# Mac/apple setup -- must appear before the first "project()" line"
set(CMAKE_OSX_DEPLOYMENT_TARGET "10.12")
if(NOT DEFINED CMAKE_OSX_SYSROOT)
    # Tells Mac builds to use the current SDK's headers & libs, not what's in the OS.
    set(CMAKE_OSX_SYSROOT macosx)
endif()

if(NOT CMAKE_BUILD_TYPE)
    message(STATUS "Setting build type to 'Debug' as none was specified.")
    set(CMAKE_BUILD_TYPE "Debug" CACHE STRING "Choose the type of build." FORCE)
endif()

if(MSVC)
    add_definitions(-D_WIN32_WINNT=0x0A00)
endif()

project(TestServerVendor)

include(FetchContent)

FetchContent_Declare(
        civetweb
        GIT_REPOSITORY https://github.com/couchbasedeps/civetweb
        GIT_TAG cbl_c_testserver
        GIT_SHALLOW TRUE
)

# Downstream does not support CMP0077 NEW
# so need these redundant options with the actual
# value I want
option(CIVETWEB_SERVE_NO_FILES "Configures the server to serve no static files" ON)
option(CIVETWEB_DISABLE_CGI "Disables CGI, so theserver will not execute CGI scripts" ON)
option(CIVETWEB_DISABLE_CACHING "Disables caching, so that no timegm is used." ON)
option(CIVETWEB_ENABLE_SSL "Enables the secure socket layer" OFF)
option(CIVETWEB_ENABLE_ASAN "Enable ASAN in debug mode" OFF)
option(CIVETWEB_BUILD_TESTING "Enable automated testing of civetweb" OFF)
option(CIVETWEB_ENABLE_SERVER_EXECUTABLE "Enable building of the server executable" OFF)
option(CIVETWEB_ENABLE_DEBUG_TOOLS "For Debug builds enable verbose logging and assertions" OFF)
option(BUILD_SHARED_LIBS "Build shared libraries" OFF)
set(BUILD_SHARED_LIBS OFF) # Ugh how many times do I have to tell you?!

message(STATUS "Fetching civetweb...")
FetchContent_MakeAvailable(civetweb)

FetchContent_Declare(
        json
        GIT_REPOSITORY https://github.com/ArthurSonzogni/nlohmann_json_cmake_fetchcontent
        GIT_TAG v3.9.1
        GIT_SHALLOW TRUE
)
message(STATUS "Fetching json...")
FetchContent_MakeAvailable(json)

if(MSVC)
    FetchContent_Declare(
            zlib
            GIT_REPOSITORY https://github.com/couchbasedeps/zlib
            GIT_TAG master
            GIT_SHALLOW TRUE
    )

    message(STATUS "Fetching zlib...")
    FetchContent_MakeAvailable(zlib)

    if(${CMAKE_BUILD_TYPE} STREQUAL "Debug")
        set(ZLIB_LIBRARY ${zlib_BINARY_DIR}/Debug/zlibstaticd.lib)
    else()
        set(ZLIB_LIBRARY ${zlib_BINARY_DIR}/${CMAKE_BUILD_TYPE}/zlibstatic.lib)
    endif()
    
    set(ZLIB_INCLUDE_DIR ${zlib_SOURCE_DIR})
    list(APPEND ZLIB_INCLUDE_DIR ${zlib_BINARY_DIR})
    target_include_directories(zlibstatic PRIVATE ${ZLIB_INCLUDE_DIR})
endif()

FetchContent_Declare(
        ixwebsocket
        GIT_REPOSITORY https://github.com/machinezone/IXWebSocket.git
        GIT_TAG v11.4.5
)
message(STATUS "Fetching IXWebSocket...")
FetchContent_MakeAvailable(ixwebsocket)

FetchContent_Declare(
        libzip
        GIT_REPOSITORY https://github.com/nih-at/libzip
        GIT_TAG v1.7.3
        GIT_SHALLOW TRUE
)

option(BUILD_TOOLS "" OFF)
option(BUILD_DOC "" OFF)
option(BUILD_REGRESS "" OFF)
option(BUILD_EXAMPLES "" OFF)
option(ENABLE_BZIP2 "" OFF)
option(ENABLE_LZMA "" OFF)
option(ENABLE_WINDOWS_CRYPTO "" OFF)
option(ENABLE_OPENSSL "" OFF)
message(STATUS "Fetching libzip...")
FetchContent_MakeAvailable(libzip)
target_include_directories(zip PRIVATE ${zlib_BINARY_DIR})
