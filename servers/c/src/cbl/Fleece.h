#pragma once

#include "CBLHeader.h"
#include FLEECE_HEADER(Fleece.h)

#include <nlohmann/json.hpp>
#include <unordered_map>
#include <vector>

namespace ts_support::fleece {
    nlohmann::json toJSON(FLValue value);

    void updateProperties(FLMutableDict dict,
                          const std::vector<std::unordered_map<std::string, nlohmann::json>> &updates);

    void removeProperties(FLMutableDict dict, const std::vector<std::string> &keyPaths);

    FLValue valueAtKeyPath(FLDict dict, const std::string &keyPath);

    bool valueIsEquals(FLValue value1, FLValue value2, std::string &outKeyPath);
}