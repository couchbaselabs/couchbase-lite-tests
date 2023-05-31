#include "Request.h"
#include <civetweb.h>
#include <sstream>
#include "TestServer.h"

using namespace nlohmann;
using namespace std;

Request::Request(mg_connection *conn, const TestServer *server) {
    const mg_request_info *info = mg_get_request_info(conn);
    _method = info->request_method;
    _path = info->request_uri;
    _conn = conn;
    _server = server;
}

int Request::version() const {
    auto version = mg_get_header(_conn, "CBLTest-API-Version");
    if (!version) { return -1; }
    try { return stoi(version); } catch (...) { return -1; }
}

std::string Request::clientUUID() const {
    return mg_get_header(_conn, "CBLTest-Client-ID");
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
    return respond(200, [&]() {
        mg_send_http_ok(_conn, nullptr, 0);
    });
}

int Request::respondWithJSON(const json &json) const {
    return respond(200, [&]() {
        string jsonStr = json.dump();
        mg_send_http_ok(_conn, "application/json", (long long) jsonStr.size());
        mg_write(_conn, jsonStr.c_str(), jsonStr.size());
    });
}

int Request::respondWithError(int code, const char *message) const {
    assert(code >= 400);
    return respond(code, [&]() {
        auto msg = message == nullptr ? mg_get_response_code_text(_conn, code) : message;
        mg_send_http_error(_conn, code, "%s", msg);
    });
}

void Request::addCommonResponseHeaders() const {
    mg_response_header_add(_conn, "CBLTest-API-Version", to_string(TestServer::API_VERSION).c_str(), -1);
    mg_response_header_add(_conn, "CBLTest-Server-ID", _server->serverUUID().c_str(), -1);
}

int Request::respond(int status, std::function<void()> respondFunction) const {
    mg_response_header_start(_conn, status);
    addCommonResponseHeaders();
    respondFunction();
    mg_response_header_send(_conn);
    return status;
}
