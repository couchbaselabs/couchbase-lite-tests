#pragma once

#include <algorithm>
#include <string>
#include <vector>
#include <sstream>

namespace ts::support::str {
    template<typename ... Args>
    std::string concat(const Args &... args) {
        std::stringstream ss;
        int unpack[] = {0, ((void) (ss << args), 0) ...};
        static_cast<void>(unpack);
        return ss.str();
    }

    std::vector<std::string> split(const std::string &str, char delimeter);

    std::string tolower(const std::string &str);

    template<typename E>
    class StringEnum {
    public:
        StringEnum(const std::vector<std::string> &values, const std::vector<E> enums) {
            assert(values.size() == enums.size());
            for (auto val: values) {
                _values.push_back(tolower(val));
            }
            _enumValues = enums;
        }

        E value(const std::string &value) {
            auto val = tolower(value);
            auto it = std::find(_values.begin(), _values.end(), val);
            if (it == _values.end()) {
                throw std::logic_error("Invalid enum value : " + value);
            }
            auto index = it - _values.begin();
            return _enumValues[index];
        }

    private:
        std::vector<std::string> _values;
        std::vector<E> _enumValues;
    };
}