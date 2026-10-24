#pragma once

#include "CBLHeader.h"
#include CBL_HEADER(CBLBase.h)
#include "HTTPStatus.h"

#include <nlohmann/json.hpp>
#include <stdexcept>
#include <string>
#include <sstream>
#include <utility>

namespace ts::support::error {
    // An error caused by the client's request; responded to with the given status.
    class ClientError : public std::exception {
    public:
        explicit ClientError(std::string message, HTTPStatus status = HTTPStatus::BadRequest)
                : _message(std::move(message)), _status(status) {}

        [[nodiscard]] const char *what() const noexcept override { return _message.c_str(); }

        [[nodiscard]] HTTPStatus status() const { return _status; }

    private:
        std::string _message;
        HTTPStatus _status;
    };

    class CBLException : public std::exception {
    public:
        explicit CBLException(const CBLError &error);

        [[nodiscard]] const char *what() const noexcept override { return _what.c_str(); }

        [[nodiscard]] const CBLError &error() const { return _error; }

        [[nodiscard]] nlohmann::json json() const;

    private:
        std::string _what;
        CBLError _error;
    };

    class RequestError : public std::logic_error {
    public:
        explicit RequestError(const std::string &s) : logic_error(s) {}
    };

    static inline void CheckBody(const nlohmann::json &body) {
        if (!body.is_object()) {
            throw ts::support::error::RequestError("Request body is not json object");
        }
    }
}