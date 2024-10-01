#pragma once

// support
#include "Error.h"

// lib
#include <nlohmann/json.hpp>
#include <string>

namespace ts::support::json_util {
    template<typename T>
    T
    GetValue(const nlohmann::json &dict, const std::string &key) {
        if (!dict.contains(key)) {
            throw error::RequestError("'" + key + "' is required");
        }

        try {
            return dict[key].get<T>();
        } catch (const std::exception &e) {
            throw error::RequestError("'" + key + "' has invalid value type : " + e.what());
        }
    }

    template<typename T>
    T
    GetValue(const nlohmann::json &dict, const std::string &key, T defaultValue) {
        if (!dict.contains(key)) {
            return defaultValue;
        }

        try {
            return dict[key].get<T>();
        } catch (const std::exception &e) {
            throw error::RequestError("'" + key + "' has invalid value type : " + e.what());
        }
    }

    template<typename T>
    std::optional<T>
    GetOptValue(const nlohmann::json &dict, const std::string &key, bool mustExist = false,
                const std::string &pathInfo = "") {
        if (!dict.contains(key)) {
            if (mustExist) {
                throw error::RequestError("'" + key + "' is required");
            }
            return std::nullopt;
        }
        try {
            auto val = dict[key];
            if (val.is_null()) {
                return std::nullopt;
            }
            return val.get<T>();
        } catch (const std::exception &e) {
            std::string pathName = pathInfo.empty() ? key : pathInfo;
            throw error::RequestError("'" + pathName + "' has invalid value type : " + e.what());
        }
    }

    static inline void
    CheckIsObject(const nlohmann::json &obj, const std::string &key,
                  const std::string &pathInfo = "") {
        if (!obj.is_object()) {
            std::string pathName = pathInfo.empty() ? key : pathInfo;
            throw error::RequestError("'" + pathName + "' is not a JSON object");
        }
    }
}