#pragma once

#include "CBLHeader.h"
#include FLEECE_HEADER(Fleece.h)

#include <nlohmann/json.hpp>
#include <unordered_map>
#include <vector>

namespace ts_support::fleece {
    nlohmann::json toJSON(FLValue value);

    void updateProperty(FLMutableDict dict, FLSlice keyPath, const nlohmann::json &value);

    void removeProperty(FLMutableDict dict, FLSlice keyPath);

    void updateProperties(FLMutableDict dict, std::vector<std::unordered_map<std::string, nlohmann::json>> updates);

    void removeProperties(FLMutableDict dict, std::vector<std::string> keyPaths);

    FLDict compareDicts(FLDict dict1, FLDict dict2);
}
