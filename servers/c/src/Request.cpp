#include "Request.h"
#include <civetweb.h>
#include <sstream>

using namespace nlohmann;
using namespace std;

Request::Request(mg_connection *conn) {
    const mg_request_info *info = mg_get_request_info(conn);
    _method = info->request_method;
    _path = info->request_uri;
    _conn = conn;
}

int Request::version() const {
    return 1;
}

const nlohmann::json &Request::jsonBody() {
    if (_jsonBody.empty()) {
        stringstream s;
        char buf[8192];
        int r = mg_read(_conn, buf, 8192);
        while (r > 0) {
            s.write(buf, r);
            r = mg_read(_conn, buf, 8192);
        }
        if (s.tellp() >= 2) {
            s >> _jsonBody;
        }
    }
    return _jsonBody;
}

int Request::respondWithOK() const {
    mg_send_http_ok(_conn, nullptr, 0);
    return 200;
}

int Request::respondWithJSON(const json &json) const {
    string jsonStr = json.dump();
    mg_send_http_ok(_conn, "application/json", (long long) jsonStr.size());
    mg_write(_conn, jsonStr.c_str(), jsonStr.size());
    return 200;
}

int Request::respondWithError(int code, const char *message) const {
    assert(code >= 400);
    auto msg = message == nullptr ? mg_get_response_code_text(_conn, code) : message;
    mg_send_http_error(_conn, code, "%s", msg);
    return code;
}

