cmake_minimum_required(VERSION 3.11)
cmake_policy(VERSION 3.11)
cmake_policy(SET CMP0077 NEW)

project(TestServer)

set(CMAKE_CXX_STANDARD 17)

add_subdirectory(vendor)

get_directory_property(civetweb_SOURCE_DIR DIRECTORY vendor DEFINITION civetweb_SOURCE_DIR)

message(STATUS ${CMAKE_LIBRARY_ARCHITECTURE})

find_package(CouchbaseLite 3.1.0 REQUIRED PATHS lib/libcblite)

set(
        SOURCE_FILES
        src/main.cpp
        src/TestServer.cpp src/TestServer.h
        src/Dispatcher.cpp src/Dispatcher.h
        src/Request.cpp src/Request.h)

add_executable(testserver ${SOURCE_FILES})

target_link_libraries(
        testserver PRIVATE
        civetweb-c-library
        nlohmann_json::nlohmann_json
        cblite
        zip
)

target_include_directories(
        testserver PRIVATE
        ${civetweb_SOURCE_DIR}/include
)

target_compile_definitions(
        testserver PRIVATE
        -DJSON_USE_IMPLICIT_CONVERSIONS=0
        -DHAS_UNCAUGHT_EXCEPTIONS=1
)