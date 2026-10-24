#include "Request.h"
#include "TestServer.h"

// support
#include "Log.h"

// lib
#include <civetweb.h>
#include <sstream>

using namespace nlohmann;
using namespace std;
using namespace ts::log;
using namespace ts::support;
using namespace ts::support::error;

namespace ts {
    Request::Request(mg_connection *conn, const Dispatcher *dispatcher) {
        const mg_request_info *info = mg_get_request_info(conn);
        _method = info->request_method;
        _path = info->request_uri;
        _conn = conn;
        _dispatcher = dispatcher;
    }

    int Request::version() const {
        auto version = mg_get_header(_conn, "CBLTest-API-Version");
        if (!version) { return -1; }
        try { return stoi(version); } catch (...) { return -1; }
    }

    std::string Request::clientID() const {
        return mg_get_header(_conn, "CBLTest-Client-ID");
    }

    const nlohmann::json &Request::jsonBody() {
        if (_jsonBody.empty()) {
            try {
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
            } catch (const std::exception &e) {
                string message = string("Invalid JSON in request body : ") + e.what();
                throw RequestError(message);
            }
        }
        return _jsonBody;
    }

    int Request::respondWithOK() const {
        return respond(HTTPStatus::OK);
    }

    int Request::respondWithJSON(const json &json) const {
        auto jsonBody = json.dump();
        return respond(HTTPStatus::OK, jsonBody);
    }

    int Request::respondWithError(HTTPStatus status, const char *message) const {
        nlohmann::json json = json::object();
        json["domain"] = "TESTSERVER";
        json["code"] = static_cast<int>(status);
        json["message"] = message;
        auto jsonBody = json.dump();
        return respond(status, jsonBody);
    }

    int Request::respondWithRequestError(const char *message) const {
        return respondWithError(HTTPStatus::BadRequest, message);
    }

    int Request::respondWithServerError(const char *message) const {
        return respondWithError(HTTPStatus::InternalServerError, message);
    }

    int Request::respondWithCBLError(const CBLException &exception) const {
        auto json = exception.json();
        return respond(HTTPStatus::BadRequest, json.dump());
    }

    void Request::addCommonResponseHeaders() const {
        mg_response_header_add(_conn, "CBLTest-API-Version",
                               to_string(TestServer::API_VERSION).c_str(), -1);
        mg_response_header_add(_conn, "CBLTest-Server-ID",
                               _dispatcher->server()->serverUUID().c_str(), -1);
        mg_response_header_add(_conn, "Cache-Control",
                               "no-cache, no-store, must-revalidate, private, max-age=0", -1);
        mg_response_header_add(_conn, "Expires", "0", -1);
        mg_response_header_add(_conn, "Pragma", "no-cache", -1);
    }

    int Request::respond(HTTPStatus status, const optional <string> &json) const {
        auto code = static_cast<int>(status);
        mg_response_header_start(_conn, code);
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

        if (status == HTTPStatus::OK) {
            Log::log(LogLevel::info, "Response %s : OK (%d)", name().c_str(), code);
        } else {
            if (json) {
                Log::log(LogLevel::info, "Response %s : Error (%d) : %s", name().c_str(), code,
                         json->c_str());
            } else {
                Log::log(LogLevel::info, "Response %s : Error (%d)", name().c_str(), code);
            }
        }
        return code;
    }
}