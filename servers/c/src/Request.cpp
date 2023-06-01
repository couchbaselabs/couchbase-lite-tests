#include "Request.h"
#include <civetweb.h>
#include <sstream>
#include "TestServer.h"

using namespace nlohmann;
using namespace std;
using namespace ts_support::exception;

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
    return respond(200);
}

int Request::respondWithJSON(const json &json) const {
    auto jsonBody = json.dump();
    return respond(200, jsonBody);
}

int Request::respondWithServerError(const char *message, int code) const {
    assert(code >= 400);
    nlohmann::json json = json::object();
    json["domain"] = "TESTSERVER";
    json["code"] = code;
    json["message"] = message;
    auto jsonBody = json.dump();
    return respond(code, jsonBody);
}

int Request::respondWithCBLError(const ts_support::exception::CBLException &exception) const {
    auto jsonBody = exception.json();
    return respond(400, jsonBody);
}

void Request::addCommonResponseHeaders() const {
    mg_response_header_add(_conn, "CBLTest-API-Version", to_string(TestServer::API_VERSION).c_str(), -1);
    mg_response_header_add(_conn, "CBLTest-Server-ID", _server->serverUUID().c_str(), -1);
    mg_response_header_add(_conn, "Cache-Control", "no-cache, no-store, must-revalidate, private, max-age=0", -1);
    mg_response_header_add(_conn, "Expires", "0", -1);
    mg_response_header_add(_conn, "Pragma", "no-cache", -1);
}

int Request::respond(int status, const optional<string> &json) const {
    mg_response_header_start(_conn, status);
    addCommonResponseHeaders();
    if (json) {
        mg_response_header_add(_conn, "Content-Type", "application/json", -1);
        mg_response_header_add(_conn, "Content-Length", to_string(json->size()).c_str(), -1);
    } else {
        mg_response_header_add(_conn, "Content-Type", "text/html", -1);
        mg_response_header_add(_conn, "Content-Length", "0", -1);
    }
    mg_response_header_send(_conn);
    if (json) {
        mg_write(_conn, json->c_str(), json->size());
    }
    return status;
}