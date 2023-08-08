#include "KeyPath.h"

#include <sstream>

using namespace std;
using namespace ts_support::keypath;

static uint32_t toArrayIndex(const std::string &str) {
    stringstream ss(str);
    uint32_t result;
    ss >> result;
    if (ss.fail()) {
        throw logic_error("Invalid array index");
    }
    return result;
}

/** Parse dict key starting from the giving startIndex. Return a pair of parsed result
 * in Path object and the end index of the dict key in the given keyPath. */
static pair<Path, size_t> parseDict(const string &keyPath, size_t startIndex) {
    string key;

    size_t i = startIndex;
    if (keyPath[i] == '.') {
        i++;
    }

    while (i < keyPath.length()) {
        auto ch = keyPath[i];
        if (ch == '\\') {
            if (i + 1 < keyPath.length()) {
                key.push_back(keyPath[i + 1]);
                i += 2;
            } else {
                throw KeyPathError(keyPath, "Unescaped special character '\' found");
            }
        } else if (ch == '.' || ch == '[') {
            i--;
            break;
        } else if (ch == ']') {
            throw KeyPathError(keyPath, "Unescaped special character ']' found");
        } else {
            key.push_back(keyPath[i]);
            i++;
        }
    }

    if (key.length() == 0) {
        throw KeyPathError(keyPath, "Empty key found");
    }
    return make_pair(Path{key, nullopt}, i);
}

/** Parse array index starting from the giving startIndex. Return a pair of parsed result
 * in a pair of Path object and the end index of the array index (']') in the given keyPath. */
static pair<Path, size_t> parseArray(const string &keyPath, size_t startIndex) {
    string index;

    size_t i = startIndex;
    if (keyPath[i] == '[') {
        i++;
    } else {
        throw KeyPathError(keyPath, "Array path not start with [");
    }

    while (i < keyPath.length()) {
        auto ch = keyPath[i];
        if (isdigit(ch)) {
            index.push_back(ch);
            i++;
        } else if (ch == ']') {
            try {
                auto result = toArrayIndex(index);
                return make_pair(Path{nullopt, result}, i);
            } catch (exception &e) {
                throw KeyPathError(keyPath, e.what());
            }
        } else {
            throw KeyPathError(keyPath, "Invalid array index found");
        }
    }

    throw KeyPathError(keyPath, "Close bracket for an array index not found");
}

vector<Path> ts_support::keypath::parseKeyPath(const string &keyPath) {
    if (keyPath.length() == 0) {
        throw KeyPathError(keyPath, "Empty key path is not allowed");
    }

    vector<Path> paths;
    size_t i = 0;
    while (i < keyPath.length()) {
        char ch = keyPath[i];
        if (i == 0) {
            // Do not allow the key path to start with $ unless it is used with '.' or being escaped.
            // Do not allow the key path to start with '.'.
            if (ch == '$') {
                if (i < (keyPath.length() - 1) && keyPath[i + 1] == '.') {
                    ch = keyPath[++i]; // Skip '$'
                } else {
                    throw KeyPathError(keyPath, "The prefix '$' is not followed by '.'");
                }
            } else if (ch == '.') {
                throw KeyPathError(keyPath, "Key path cannot start with '.'");
            }
        }

        if (ch == '.' || i == 0) {
            auto result = parseDict(keyPath, i);
            paths.push_back(result.first);
            i = result.second + 1;
        } else if (ch == '[') {
            auto result = parseArray(keyPath, i);
            paths.push_back(result.first);
            i = result.second + 1;
        } else {
            throw KeyPathError(keyPath, "A character '" + string(1, ch) + "' is not allowed at index " + to_string(i));
        }
    }
    return paths;
}