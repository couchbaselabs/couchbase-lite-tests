#include "Error.h"
#include "Defer.h"

using namespace std;
using namespace nlohmann;

namespace ts::support::error {
    string errorMessage(const CBLError &error) {
        FLSliceResult messageVal = CBLError_Message(&error);
        DEFER { FLSliceResult_Release(messageVal); };
        return string(static_cast<const char *>(messageVal.buf), messageVal.size);
    }

    CBLErrorDomain crossPlatformDomain(const CBLError &error) {
        return (error.domain == kCBLNetworkDomain || error.domain == kCBLWebSocketDomain) ? kCBLDomain : error.domain;
    }

    int crossPlatformCode(const CBLError &error) {
        if (error.domain == kCBLNetworkDomain) {
            return error.code + 5000;
        } else if (error.domain == kCBLWebSocketDomain) {
            return error.code + 10000;
        } else {
            return error.code;
        }
    }

    CBLException::CBLException(const CBLError &error) {
        _error = error;

        stringstream ss;
        ss << "Couchbase Lite Error : "
           << (int) crossPlatformCode(_error) << "/"
           << crossPlatformCode(_error) << ", "
           << errorMessage(_error);
        _what = ss.str();
    }

    json CBLException::json() const {
        nlohmann::json result = json::object();
        auto domain = crossPlatformDomain(_error);
        switch (domain) {
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
            default:
                result["domain"] = "CBL";
        }
        result["code"] = crossPlatformCode(_error);
        result["message"] = errorMessage(_error);
        return result;
    }
}