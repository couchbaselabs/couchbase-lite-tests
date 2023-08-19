#pragma once

#include <string>

struct CBLCollection;
struct CBLDocument;

class CollectionSpec {
public:
    explicit CollectionSpec(const std::string &fullName) {
        auto pos = fullName.find('.');
        if (pos != std::string::npos) {
            _scope = fullName.substr(0, pos);
            _name = fullName.substr(pos + 1);
            _fullName = fullName;
        } else {
            _scope = "_default";
            _name = fullName;
            _fullName = _scope + "." + _name;
        }
    }

    explicit CollectionSpec(const CBLCollection *collection);

    explicit CollectionSpec(const CBLDocument *doc);

    CollectionSpec(const std::string &scope, const std::string &name);

    [[nodiscard]] const std::string &scope() const { return _scope; }

    [[nodiscard]] const std::string &name() const { return _name; }

    [[nodiscard]] const std::string &fullName() const { return _fullName; }

private:
    std::string _scope;
    std::string _name;
    std::string _fullName;
};
