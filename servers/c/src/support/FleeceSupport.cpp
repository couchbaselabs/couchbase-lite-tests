#include "FleeceSupport.h"
#include "Define.h"

using namespace std;
using namespace nlohmann;

void ts_support::fleece::setSlotValue(FLSlot slot, const json &json) { // NOLINT(misc-no-recursion)
    switch (json.type()) {
        case json::value_t::string: {
            auto s = json.get<string>();
            FLString val = {s.data(), s.size()};
            FLSlot_SetString(slot, val);
            break;
        }
        case json::value_t::number_float:
            FLSlot_SetDouble(slot, json.get<double>());
            break;
        case json::value_t::number_integer:
            FLSlot_SetInt(slot, json.get<int64_t>());
            break;
        case json::value_t::number_unsigned:
            FLSlot_SetUInt(slot, json.get<uint64_t>());
            break;
        case json::value_t::boolean:
            FLSlot_SetBool(slot, json.get<bool>());
            break;
        case json::value_t::null:
            FLSlot_SetNull(slot);
            break;
        case json::value_t::object: {
            FLMutableDict dict = FLMutableDict_New();
            for (const auto &[key, value]: json.items()) {
                FLSlot dictSlot = FLMutableDict_Set(dict, FLS(key));
                setSlotValue(dictSlot, value);
            }
            FLSlot_SetDict(slot, dict);
            FLMutableDict_Release(dict);
            break;
        }
        case json::value_t::array: {
            FLMutableArray array = FLMutableArray_New();
            for (const auto &value: json) {
                FLSlot arraySlot = FLMutableArray_Append(array);
                setSlotValue(arraySlot, value);
            }
            FLSlot_SetArray(slot, array);
            FLMutableArray_Release(array);
            break;
        }
        case json::value_t::binary:
        case json::value_t::discarded:
        default:
            throw domain_error("Unsupported JSON value as fleece value");
    }
}
