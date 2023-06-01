#include "Exception.h"
#include "Defer.h"
#include <nlohmann/json.hpp>

using namespace nlohmann;

string errorMessage(const CBLError &error) {
    FLSliceResult messageVal = CBLError_Message(&error);
    DEFER { FLSliceResult_Release(messageVal); };
    return string(static_cast<const char *>(messageVal.buf), messageVal.size);
}

ts_support::exception::CBLException::CBLException(const CBLError &error) {
    _error = error;

    stringstream ss;
    ss << "Couchbase Lite Error : "
       << (int) _error.domain << "/"
       << _error.code << ", "
       << errorMessage(_error);
    _what = ss.str();
}

std::string ts_support::exception::CBLException::json() const {
    nlohmann::json result = json::object();
    switch (_error.domain) {
        case kCBLDomain:
            result["domain"] = "CBL";
            break;
        case kCBLPOSIXDomain:
            result["domain"] = "POSIX";
            break;
        case kCBLSQLiteDomain:
            result["domain"] = "SQLITE";
            break;
        case kCBLFleeceDomain:
            result["domain"] = "FLEECE";
            break;
        case kCBLNetworkDomain:
            result["domain"] = "NETWORK";
            break;
        case kCBLWebSocketDomain:
            result["domain"] = "WEBSOCKET";
            break;
        default:
            result["domain"] = "CBL";
    }
    result["code"] = _error.code;
    result["message"] = errorMessage(_error);
    return result.dump();
}
