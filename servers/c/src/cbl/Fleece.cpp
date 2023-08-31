#include "Fleece.h"
#include "Define.h"
#include "KeyPath.h"
#include "JSON.h"

#include FLEECE_HEADER(FLExpert.h)

#include <unordered_set>

using namespace std;
using namespace nlohmann;
using namespace ts_support::fleece;
using namespace ts::support::json_util;

void setSlotValue(FLSlot slot, const json &value) { // NOLINT(misc-no-recursion)
    switch (value.type()) {
        case json::value_t::string: {
            auto s = value.get<string>();
            FLString val = {s.data(), s.size()};
            FLSlot_SetString(slot, val);
            break;
        }
        case json::value_t::number_float:
            FLSlot_SetDouble(slot, value.get<double>());
            break;
        case json::value_t::number_integer:
            FLSlot_SetInt(slot, value.get<int64_t>());
            break;
        case json::value_t::number_unsigned:
            FLSlot_SetUInt(slot, value.get<uint64_t>());
            break;
        case json::value_t::boolean:
            FLSlot_SetBool(slot, value.get<bool>());
            break;
        case json::value_t::null:
            FLSlot_SetNull(slot);
            break;
        case json::value_t::object: {
            FLMutableDict dict = FLMutableDict_New();
            for (const auto &[key, val]: value.items()) {
                FLSlot dictSlot = FLMutableDict_Set(dict, FLS(key));
                setSlotValue(dictSlot, val);
            }
            FLSlot_SetDict(slot, dict);
            FLMutableDict_Release(dict);
            break;
        }
        case json::value_t::array: {
            FLMutableArray array = FLMutableArray_New();
            for (const auto &val: value) {
                FLSlot arraySlot = FLMutableArray_Append(array);
                setSlotValue(arraySlot, val);
            }
            FLSlot_SetArray(slot, array);
            FLMutableArray_Release(array);
            break;
        }
        case json::value_t::binary:
        case json::value_t::discarded:
        default:
            throw logic_error("Cannot convert JSON value to fleece value");
    }
}

nlohmann::json ts_support::fleece::toJSON(FLValue value) { // NOLINT(misc-no-recursion)
    auto type = FLValue_GetType(value);
    switch (type) {
        case kFLNull:
            return nullptr;
        case kFLBoolean:
            return FLValue_AsBool(value);
        case kFLNumber: {
            if (FLValue_IsInteger(value)) {
                if (FLValue_IsUnsigned(value)) {
                    return FLValue_AsUnsigned(value);
                } else {
                    return FLValue_AsInt(value);
                }
            } else if (FLValue_IsDouble(value)) {
                return FLValue_AsDouble(value);
            } else {
                return FLValue_AsFloat(value);
            }
        }
        case kFLString: {
            return STR(FLValue_AsString(value));
        }
        case kFLDict: {
            json dict = json::object();
            FLDictIterator iter;
            FLDictIterator_Begin(FLValue_AsDict(value), &iter);
            FLValue val;
            while (nullptr != (val = FLDictIterator_GetValue(&iter))) {
                FLString key = FLDictIterator_GetKeyString(&iter);
                dict[STR(key)] = toJSON(val);
                FLDictIterator_Next(&iter);
            }
            return dict;
        }
        case kFLArray: {
            json array = json::array();
            FLArrayIterator iter;
            FLArrayIterator_Begin(FLValue_AsArray(value), &iter);
            FLValue val;
            while (nullptr != (val = FLArrayIterator_GetValue(&iter))) {
                array.push_back(toJSON(val));
                FLArrayIterator_Next(&iter);
            }
            return array;
        }
        default:
            throw logic_error("Cannot convert fleece value to JSON");
    }
}

FLValue getDictValue(FLDict dict, FLString key) {
    auto mDict = FLDict_AsMutable(dict);
    if (mDict) {
        auto dictVal = FLMutableDict_GetMutableDict(mDict, key);
        if (dictVal) {
            return (FLValue) dictVal;
        }
        auto arrayVal = FLMutableDict_GetMutableArray(mDict, key);
        if (arrayVal) {
            return (FLValue) arrayVal;
        }
    }
    return FLDict_Get(dict, key);
}

FLValue getArrayValue(FLArray array, uint32_t index) {
    auto mArray = FLArray_AsMutable(array);
    if (mArray) {
        auto dictVal = FLMutableArray_GetMutableDict(mArray, index);
        if (dictVal) {
            return (FLValue) dictVal;
        }
        auto arrayVal = FLMutableArray_GetMutableArray(mArray, index);
        if (arrayVal) {
            return (FLValue) arrayVal;
        }
    }
    return FLArray_Get(mArray, index);
}

/** Return dict or array as parent. If createdParent is true, the root dictionary MUST be a mutable dictionary.
 *  When parent specified in the path is not found:
 *  - If the createParent is true, the parents will be created. For array parent, the array will be resized and padded
 *    with null to cover the specified array index in the key path.
 *  - Otherwise, NULL FLValue will be returned. */
FLValue getParent(FLDict root, const string &keyPath, bool createParent) {
    FLValue parent = createParent ? (FLValue) FLDict_AsMutable(root) : (FLValue) root;
    if (!parent) {
        throw runtime_error("Invalid root dictionary");
    }

    int i = 0;
    auto paths = ts_support::keypath::parseKeyPath(keyPath);
    for (auto &path: paths) {
        if (path.key) { // Dict path
            auto dict = FLValue_AsDict(parent);
            if (!dict) {
                throw logic_error("Mismatch type between key path and value (not dict value) : " + keyPath);
            }

            // Last path component, return the current dict
            if (paths.size() == i + 1) {
                parent = (FLValue) dict;
                break;
            }

            // Look ahead and create a new parent for non-existing path:
            auto key = FLS(path.key.value());
            auto nextParent = getDictValue(dict, key);
            if (nextParent == nullptr) {
                if (!createParent) {
                    parent = kFLNullValue;
                    break;
                }

                auto mDict = FLDict_AsMutable(dict);
                assert(mDict);

                if (paths[i + 1].key) {
                    auto newDict = FLMutableDict_New();
                    FLMutableDict_SetDict(mDict, key, newDict);
                    FLMutableDict_Release(newDict);
                    nextParent = (FLValue) newDict;
                } else {
                    auto newArray = FLMutableArray_New();
                    FLMutableDict_SetArray(mDict, key, newArray);
                    FLMutableArray_Release(newArray);
                    nextParent = (FLValue) newArray;
                }
            }
            parent = nextParent;
        } else { // Array path
            auto array = FLValue_AsArray(parent);
            if (!array) {
                throw logic_error("Mismatch type between key path and value (not array value) : " + keyPath);
            }

            // Resize and pad with null if needed:
            auto index = path.index.value();
            bool resize = index >= FLArray_Count(array);
            if (resize) {
                if (!createParent) {
                    parent = kFLNullValue;
                    break;
                }

                auto mArray = FLArray_AsMutable(array);
                assert(mArray);

                FLMutableArray_Resize(mArray, index + 1);
            }

            // Last path component, return the current array
            if (paths.size() == i + 1) {
                parent = (FLValue) array;
                break;
            }

            // Look ahead and create a new parent for non-existing path:
            auto nextParent = getArrayValue(array, index);
            if (nextParent == nullptr || resize) {
                if (!createParent) {
                    return kFLNullValue;
                }

                auto mArray = FLArray_AsMutable(array);
                assert(mArray);

                if (paths[i + 1].key) { // Dict path
                    auto newDict = FLMutableDict_New();
                    FLMutableArray_SetDict(mArray, index, newDict);
                    FLMutableDict_Release(newDict);
                    nextParent = (FLValue) newDict;
                } else {
                    auto newArray = FLMutableArray_New();
                    FLMutableArray_SetArray(mArray, index, newArray);
                    FLMutableArray_Release(newArray);
                    nextParent = (FLValue) newArray;
                }
            }
            parent = nextParent;
        }
        i++;
    }
    return parent;
}

void updateProperty(FLMutableDict props, FLSlice keyPath, const nlohmann::json &value) {
    auto keyPathStr = STR(keyPath);
    auto paths = ts_support::keypath::parseKeyPath(keyPathStr);
    auto parent = getParent(props, keyPathStr, true);
    if (FLValue_GetType(parent) == kFLDict) {
        FLMutableDict dict = FLDict_AsMutable(FLValue_AsDict(parent));
        auto path = paths.back();
        assert(path.key);
        auto key = FLS(path.key.value());
        auto slot = FLMutableDict_Set(dict, key);
        setSlotValue(slot, value);
    } else if (FLValue_GetType(parent) == kFLArray) {
        FLMutableArray array = FLArray_AsMutable(FLValue_AsArray(parent));
        auto path = paths.back();
        assert(!path.key);
        auto slot = FLMutableArray_Set(array, path.index.value());
        setSlotValue(slot, value);
    } else {
        throw runtime_error("Unexpected parent value");
    }
}

void removeProperty(FLMutableDict props, FLSlice keyPath) {
    auto keyPathStr = STR(keyPath);
    auto paths = ts_support::keypath::parseKeyPath(keyPathStr);
    auto parent = getParent(props, keyPathStr, false);
    if (!parent) { return; }

    if (FLValue_GetType(parent) == kFLDict) {
        FLMutableDict dict = FLDict_AsMutable(FLValue_AsDict(parent));
        auto path = paths.back();
        assert(path.key);
        auto key = FLS(path.key.value());
        FLMutableDict_Remove(dict, key);
    } else if (FLValue_GetType(parent) == kFLArray) {
        FLMutableArray array = FLArray_AsMutable(FLValue_AsArray(parent));
        auto path = paths.back();
        assert(!path.key);
        FLMutableArray_Remove(array, path.index.value(), 1);
    }
}

void updateProperties(FLMutableDict dict, const vector<unordered_map<string, json>> &updates) {
    for (auto &keyPaths: updates) {
        for (auto &keyPath: keyPaths) {
            updateProperty(dict, FLS(keyPath.first), keyPath.second);
        }
    }
}

void updateBlobProperty(FLMutableDict props, FLSlice keyPath, CBLBlob *blob) {
    if (!blob) {
        throw runtime_error("Blob for updating blob is null.");
    }

    auto keyPathStr = STR(keyPath);
    auto paths = ts_support::keypath::parseKeyPath(keyPathStr);
    auto parent = getParent(props, keyPathStr, true);
    if (FLValue_GetType(parent) == kFLDict) {
        FLMutableDict dict = FLDict_AsMutable(FLValue_AsDict(parent));
        auto path = paths.back();
        assert(path.key);
        auto key = FLS(path.key.value());
        auto slot = FLMutableDict_Set(dict, key);
        FLSlot_SetBlob(slot, blob);
    } else if (FLValue_GetType(parent) == kFLArray) {
        FLMutableArray array = FLArray_AsMutable(FLValue_AsArray(parent));
        auto path = paths.back();
        assert(!path.key);
        auto slot = FLMutableArray_Set(array, path.index.value());
        FLSlot_SetBlob(slot, blob);
    } else {
        throw runtime_error("Unexpected parent value found when updating blob");
    }
}

void updateBlobs(FLMutableDict dict, const unordered_map<std::string, CBLBlob *> &updates) {
    for (auto &update: updates) {
        updateBlobProperty(dict, FLS(update.first), update.second);
    }
}

void removeProperties(FLMutableDict dict, const vector<string> &keyPaths) {
    for (auto &keyPath: keyPaths) {
        removeProperty(dict, FLS(keyPath));
    }
}

void ts_support::fleece::applyDeltaUpdates(FLMutableDict dict, const json &delta, const BlobAccessor &blobAccessor) {
    if (delta.contains("removedProperties")) {
        auto keyPaths = GetValue<vector<string>>(delta, "removedProperties");
        removeProperties(dict, keyPaths);
    }

    if (delta.contains("updatedProperties")) {
        auto updateItems = GetValue<vector<unordered_map<string, json>>>(delta, "updatedProperties");
        updateProperties(dict, updateItems);
    }

    if (delta.contains("updatedBlobs")) {
        auto updates = GetValue<unordered_map<string, string>>(delta, "updatedBlobs");
        unordered_map<string, CBLBlob *> blobs;
        for (auto &update: updates) {
            auto blob = blobAccessor(update.second);
            blobs[update.first] = blob;
        }
        updateBlobs(dict, blobs);
    }
}

FLValue ts_support::fleece::valueAtKeyPath(FLDict dict, const std::string &keyPath) {
    auto paths = ts_support::keypath::parseKeyPath(keyPath);
    auto parent = getParent(dict, keyPath, false);
    if (!parent) { return nullptr; }
    if (FLValue_GetType(parent) == kFLDict) {
        auto path = paths.back();
        assert(path.key);
        return FLDict_Get(FLValue_AsDict(parent), FLS(path.key.value()));
    } else if (FLValue_GetType(parent) == kFLArray) {
        auto path = paths.back();
        assert(!path.key);
        return FLArray_Get(FLValue_AsArray(parent), path.index.value());
    }
    return nullptr;
}

void prependPath(FLString path, std::string &keypath) {
    if (!keypath.empty() && keypath[0] != '[') {
        keypath.insert(0, ".");
    }
    keypath.insert(0, STR(path));
}

void prependPath(uint32_t index, std::string &keypath) {
    if (!keypath.empty() && keypath[0] != '[') {
        keypath.insert(0, ".");
    }
    keypath.insert(0, string("[").append(to_string(index)).append("]"));
}

bool dictIsEquals(FLDict dict1, FLDict dict2, std::string &keypath, const BlobValidator &blobValidator) {
    unordered_set<string> checkedKeys;
    FLDictIterator iter1;
    FLDictIterator_Begin(dict1, &iter1);
    FLValue val1;
    while (nullptr != (val1 = FLDictIterator_GetValue(&iter1))) {
        FLString key = FLDictIterator_GetKeyString(&iter1);
        auto val2 = FLDict_Get(dict2, key);
        bool isEqual = ts_support::fleece::valueIsEquals(val1, val2, keypath, blobValidator);
        if (!isEqual) {
            prependPath(key, keypath);
            return false;
        }
        checkedKeys.insert(STR(key));
        FLDictIterator_Next(&iter1);
    }

    if (checkedKeys.size() == FLDict_Count(dict2)) {
        return true;
    }

    FLDictIterator iter2;
    FLDictIterator_Begin(dict2, &iter2);
    FLValue val2;
    while (nullptr != (val2 = FLDictIterator_GetValue(&iter2))) {
        FLString key = FLDictIterator_GetKeyString(&iter2);
        if (checkedKeys.find(STR(key)) == checkedKeys.end()) {
            auto anotherVal = FLDict_Get(dict1, key);
            bool isEqual = ts_support::fleece::valueIsEquals(val2, anotherVal, keypath, blobValidator);
            if (!isEqual) {
                prependPath(key, keypath);
                return false;
            }
        }
        FLDictIterator_Next(&iter2);
    }
    return true;
}

bool arrayIsEquals(FLArray array1, FLArray array2, std::string &keypath, const BlobValidator &blobValidator) {
    auto count = FLArray_Count(array1);
    if (count != FLArray_Count(array2)) {
        return false;
    }
    for (uint32_t i = 0; i < count; i++) {
        auto val1 = FLArray_Get(array1, i);
        auto val2 = FLArray_Get(array2, i);
        bool isEqual = ts_support::fleece::valueIsEquals(val2, val1, keypath, blobValidator);
        if (!isEqual) {
            prependPath(i, keypath);
            return false;
        }
    }
    return true;
}

bool blobIsEquals(FLDict dict1, FLDict dict2) {
    string ignored;
    return dictIsEquals(dict1, dict2, ignored, [](FLDict blob) -> bool { return true; });
}

bool
ts_support::fleece::valueIsEquals(FLValue value1, FLValue value2, string &keypath, const BlobValidator &blobValidator) {
    if (value1 == nullptr) {
        return value2 == nullptr;
    }

    auto type = FLValue_GetType(value1);
    if (type != FLValue_GetType(value2)) {
        return false;
    }

    switch (type) {
        case kFLDict: {
            auto dict1 = FLValue_AsDict(value1);
            auto dict2 = FLValue_AsDict(value2);
            if (FLDict_IsBlob(dict1) || FLDict_IsBlob(dict2)) {
                return blobIsEquals(dict1, dict2) && blobValidator(dict1);
            }
            return dictIsEquals(dict1, dict2, keypath, blobValidator);
        }
        case kFLArray: {
            return arrayIsEquals(FLValue_AsArray(value1), FLValue_AsArray(value2), keypath, blobValidator);
        }
        default:
            return FLValue_IsEqual(value1, value2);
    }
}
