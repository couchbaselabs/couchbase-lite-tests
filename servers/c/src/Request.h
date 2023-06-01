#pragma once

#include "support/Exception.h"
#include <nlohmann/json.hpp>
#include <string>

struct mg_connection;

class TestServer;

class Request {
public:
    explicit Request(mg_connection *conn, const TestServer *server);

    // Request:
    [[nodiscard]] mg_connection *connection() const { return _conn; }

    [[nodiscard]] std::string method() const { return _method; }

    [[nodiscard]] std::string path() const { return _path; }

    [[nodiscard]] int version() const;

    [[nodiscard]] std::string clientUUID() const;

    const nlohmann::json &jsonBody();

    // Response:
    [[nodiscard]] int respondWithOK() const;

    [[nodiscard]] int respondWithJSON(const nlohmann::json &json) const;

    [[nodiscard]] int respondWithServerError(const char *message = nullptr, int code = 400) const;

    [[nodiscard]] int respondWithCBLError(const ts_support::exception::CBLException &exception) const;

private:
    void addCommonResponseHeaders() const;

    int respond(int status, const std::optional<std::string> &json = std::nullopt) const;

    mg_connection *_conn;
    const TestServer *_server;

    std::string _method;
    std::string _path;
    nlohmann::json _jsonBody;
};
