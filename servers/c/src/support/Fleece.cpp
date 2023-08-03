#include "Fleece.h"
#include "Define.h"
#include "KeyPath.h"

using namespace std;
using namespace nlohmann;

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
            throw runtime_error("Unsupported JSON value as fleece value");
    }
}

FLValue getMutableDictValue(FLMutableDict mDict, FLString key) {
    auto dict = FLMutableDict_GetMutableDict(mDict, key);
    if (dict) {
        return (FLValue) dict;
    }
    auto array = FLMutableDict_GetMutableArray(mDict, key);
    if (array) {
        return (FLValue) array;
    }
    return FLDict_Get(mDict, key);
}

FLValue getMutableArrayValue(FLMutableArray mArray, size_t index) {
    auto dict = FLMutableArray_GetMutableDict(mArray, index);
    if (dict) {
        return (FLValue) dict;
    }
    auto array = FLMutableArray_GetMutableArray(mArray, index);
    if (array) {
        return (FLValue) array;
    }
    return FLArray_Get(mArray, index);
}

void ts_support::fleece::updateProperties(FLMutableDict props, FLSlice keyPath, const nlohmann::json &value) {
    auto paths = ts_support::keypath::parseKeyPath(STR(keyPath));

    int i = 0;
    auto parent = (FLValue) props;
    for (auto &path: paths) {
        if (path.key) { // Dict path
            FLMutableDict dict = FLDict_AsMutable(FLValue_AsDict(parent));
            if (!dict) {
                throw runtime_error("Mismatch type between key path and value (not dict value) : " + STR(keyPath));
            }

            // Last path component, set the value:
            auto key = FLS(path.key.value());
            if (paths.size() == i + 1) {
                auto slot = FLMutableDict_Set(dict, key);
                setSlotValue(slot, value);
                return;
            }
            
            // Look ahead and create a new parent for non-existing path:
            FLValue val = getMutableDictValue(dict, key);
            if (val == nullptr) {
                if (paths[i + 1].key) {
                    auto newDict = FLMutableDict_New();
                    FLMutableDict_SetDict(dict, key, newDict);
                    FLMutableDict_Release(newDict);
                    val = (FLValue) newDict;
                } else {
                    auto newArray = FLMutableArray_New();
                    FLMutableDict_SetArray(dict, key, newArray);
                    FLMutableArray_Release(newArray);
                    val = (FLValue) newArray;
                }
            }
            parent = val;
        } else { // Array path
            FLMutableArray array = FLArray_AsMutable(FLValue_AsArray(parent));
            if (!array) {
                throw runtime_error("Mismatch type between key path and value (not array value) : " + STR(keyPath));
            }

            // Resize and pad with null if needed:
            auto index = path.index.value();
            bool resize = index >= FLArray_Count(array);
            if (resize) {
                FLMutableArray_Resize(array, index + 1);
            }

            // Last path component, set the value:
            if (paths.size() == i + 1) {
                auto slot = FLMutableArray_Set(array, index);
                setSlotValue(slot, value);
                return;
            }

            // Look ahead and create a new parent for non-existing path:
            FLValue val = getMutableArrayValue(array, index);
            if (val == nullptr || resize) {
                if (paths[i + 1].key) { // Dict path
                    auto newDict = FLMutableDict_New();
                    FLMutableArray_SetDict(array, index, newDict);
                    FLMutableDict_Release(newDict);
                    val = (FLValue) newDict;
                } else {
                    auto newArray = FLMutableArray_New();
                    FLMutableArray_SetArray(array, index, newArray);
                    FLMutableArray_Release(newArray);
                    val = (FLValue) newArray;
                }
            }
            parent = val;
        }
        i++;
    }
}

void ts_support::fleece::removeProperties(FLMutableDict props, FLSlice keyPath) {
    auto paths = ts_support::keypath::parseKeyPath(STR(keyPath));

    int i = 0;
    auto parent = (FLValue) props;
    for (auto &path: paths) {
        if (path.key) { // Dict path
            FLMutableDict dict = FLDict_AsMutable(FLValue_AsDict(parent));
            if (!dict) {
                throw runtime_error("Mismatch type between key path and value (not dict value) : " + STR(keyPath));
            }

            // Get value:
            auto key = FLS(path.key.value());
            auto val = getMutableDictValue(dict, key);
            if (val == nullptr) {
                return; // No value for the key
            }

            // Last component:
            if (paths.size() == i + 1) {
                FLMutableDict_Remove(dict, key);
                return;
            }

            // Set next parent:
            parent = val;
        } else { // Array path
            FLMutableArray array = FLArray_AsMutable(FLValue_AsArray(parent));
            if (!array) {
                throw runtime_error("Mismatch type between key path and value (not array value) : " + STR(keyPath));
            }

            auto index = path.index.value();
            if (index >= FLArray_Count(array)) {
                return; // index out of bound
            }

            // Last component:
            if (paths.size() == i + 1) {
                FLMutableArray_Remove(array, index, 1);
                return;
            }

            // Set next parent:
            parent = getMutableArrayValue(array, index);
        }
        i++;
    }
}
