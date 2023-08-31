#pragma once

#include "CBLHeader.h"
#include CBL_HEADER(CBLBlob.h)
#include FLEECE_HEADER(Fleece.h)

#include <nlohmann/json.hpp>
#include <unordered_map>
#include <vector>

namespace ts_support::fleece {
    nlohmann::json toJSON(FLValue value);

    using BlobAccessor = std::function<CBLBlob *(const std::string &name)>;

    void applyDeltaUpdates(FLMutableDict dict, const nlohmann::json &delta, const BlobAccessor &blobAccessor);

    FLValue valueAtKeyPath(FLDict dict, const std::string &keyPath);

    using BlobValidator = std::function<bool(FLDict blob)>;

    bool valueIsEquals(FLValue value1, FLValue value2, std::string &outKeyPath, const BlobValidator &blobValidator);
}