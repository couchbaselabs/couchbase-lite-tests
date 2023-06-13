#pragma once

#include <nlohmann/json.hpp>
#include <string>

template<typename T>
static inline T GetValue(const nlohmann::json &dict, const std::string &key, const std::string &pathInfo = "") {
    if (!dict.contains(key)) {
        throw std::domain_error("'" + key + "' is required");
    }
    try {
        return dict[key].get<T>();
    } catch (const std::exception &e) {
        std::string pathName = pathInfo.empty() ? key : pathInfo;
        throw std::domain_error("'" + pathName + "' has invalid value type : " + e.what());
    }
}

static inline void CheckIsObject(const nlohmann::json &obj, const std::string &key, const std::string &pathInfo = "") {
    if (!obj.is_object()) {
        std::string pathName = pathInfo.empty() ? key : pathInfo;
        throw std::domain_error("'" + pathName + "' is not a JSON object");
    }
}
