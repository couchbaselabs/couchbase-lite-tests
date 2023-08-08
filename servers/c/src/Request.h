#pragma once

// support
#include "Error.h"

// lib
#include <nlohmann/json.hpp>
#include <optional>
#include <string>

struct mg_connection;

namespace ts {
    class TestServer;

    class Request {
    public:
        explicit Request(mg_connection *conn, const TestServer *server);

        // Request:
        [[nodiscard]] mg_connection *connection() const { return _conn; }

        [[nodiscard]] std::string method() const { return _method; }

        [[nodiscard]] std::string path() const { return _path; }

        [[nodiscard]] std::string name() const { return _method + " " + _path; }

        [[nodiscard]] int version() const;

        [[nodiscard]] std::string clientID() const;

        const nlohmann::json &jsonBody();

        // Response:
        [[nodiscard]] int respondWithOK() const;

        [[nodiscard]] int respondWithJSON(const nlohmann::json &json) const;

        [[nodiscard]] int respondWithRequestError(const char *message) const;

        [[nodiscard]] int respondWithServerError(const char *message) const;

        [[nodiscard]] int respondWithCBLError(const ts::support::error::CBLException &exception) const;

    private:
        void addCommonResponseHeaders() const;

        [[nodiscard]] int respond(int status, const std::optional<std::string> &json = std::nullopt) const;

        mg_connection *_conn;
        const TestServer *_server;

        std::string _method;
        std::string _path;
        nlohmann::json _jsonBody;
    };
}