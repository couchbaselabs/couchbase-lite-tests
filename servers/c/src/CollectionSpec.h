#pragma once

#include <string>

class CollectionSpec {
public:
    explicit CollectionSpec(const std::string &fullName) {
        auto pos = fullName.find('.');
        if (pos != std::string::npos) {
            _scope = fullName.substr(0, pos);
            _name = fullName.substr(pos + 1);
        } else {
            _scope = "_default";
            _name = fullName;
        }
    }

    [[nodiscard]] const std::string &scope() const { return _scope; }

    [[nodiscard]] const std::string &name() const { return _name; }

private:
    std::string _scope;
    std::string _name;
};
