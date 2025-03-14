#include "Dispatcher+Common.h"
#include "TestServer.h"

// cbl
#include "CBLInfo.h"

// support
#include "Device.h"

int Dispatcher::handleGETRoot(Request &request,
                              Session *session) { // NOLINT(readability-convert-member-functions-to-static)
    json result;
    if (cbl_info::build() > 0) {
        result["version"] = cbl_info::version() + "-" + to_string(cbl_info::build());
    } else {
        result["version"] = cbl_info::version();
    }
    result["apiVersion"] = TestServer::API_VERSION;
    result["cbl"] = TestServer::CBL_PLATFORM_NAME;

    json device;
    string model = device::deviceModel();
    if (!model.empty()) {
        device["model"] = model;
    }
    string osName = device::osName();
    if (!osName.empty()) {
        device["systemName"] = osName;
    }
    string osVersion = device::osVersion();
    if (!osVersion.empty()) {
        device["systemVersion"] = osVersion;
    }
    string apiVersion = device::apiVersion();
    if (!apiVersion.empty()) {
        device["systemApiVersion"] = apiVersion;
    }
    result["device"] = device;
    result["additionalInfo"] =
        "Edition: " + cbl_info::edition() + ", Build: " + to_string(cbl_info::build());

    return request.respondWithJSON(result);
}