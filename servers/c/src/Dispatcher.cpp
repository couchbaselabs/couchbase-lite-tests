#include "Dispatcher.h"
#include <civetweb.h>
#include <sstream>

using namespace std;
using namespace placeholders;
using namespace nlohmann;

Dispatcher::Dispatcher() {
    addHandler (1, "GET", "/", bind(&Dispatcher::handleGetRoot, this, _1, _2));
}

int Dispatcher::handle(mg_connection *conn) {
    const mg_request_info* request_info = mg_get_request_info(conn);
    string method = request_info->request_method;
    string path = request_info->request_uri;

    auto handler = findHandler(1, method, path);
    if (!handler) {
        return sendErrorCode(conn, 405);
    }

    try {
        stringstream s;
        char buf[8192];
        int r = mg_read(conn, buf, 8192);
        while(r > 0) {
            s.write(buf, r);
            r = mg_read(conn, buf, 8192);
        }

        json body;
        if(s.tellp() >= 2) {
            s >> body;
        }
        handler(body, conn);
    } catch(const exception& e) {
        string msg = "Exception caught during router handling: " + string(e.what());
        return sendErrorCode(conn, 400, msg);
    }
    return 200;
}

void Dispatcher::addHandler(int version, string method, string path, const Dispatcher::Handler& handler) {
    _rules.push_back({version, method, path, handler});
}

Dispatcher::Handler Dispatcher::findHandler(int version, string method, const string& path) {
    for (auto &rule : _rules) {
        if (rule.version <= version && rule.method == method && rule.path == path) {
            return rule.handler;
        }
    }
    return nullptr;
}

int Dispatcher::sendErrorCode(mg_connection* conn, int code, const std::string& message) {
    auto msg = message.empty() ? mg_get_response_code_text(conn, code) : message.c_str();
    mg_send_http_error(conn, code, "%s", msg);
}

void Dispatcher::sendJSONResponse(mg_connection* conn, const nlohmann::json& json) {
    string encoded = json.dump();
    mg_send_http_ok(conn, "application/json", encoded.size());
    mg_write(conn, encoded.c_str(), encoded.size());
}

void Dispatcher::handleGetRoot(json& body, mg_connection *conn) {
    json result;
    result["version"] = "3.1.0";
    result["apiVersion"] = 1;
    result["cbl"] = "couchbase-lite-c";
    sendJSONResponse(conn, result);
}



