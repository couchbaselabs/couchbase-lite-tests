#include "KeyPath.h"

#include <sstream>

using namespace std;
using namespace ts_support::keypath;

static size_t toArrayIndex(const std::string &str) {
    stringstream ss(str);
    size_t result;
    ss >> result;
    if (ss.fail()) {
        throw logic_error("Invalid array index found");
    }
    return result;
}

/** Parse dict key starting from the giving startIndex. Return a pair of parsed result
 * in Path object and the end index of the dict key in the given keyPath. */
static pair<Path, size_t> parseDictKey(const string &keyPath, size_t startIndex) {
    string key;
    size_t i = startIndex;
    while (i < keyPath.length()) {
        auto ch = keyPath[i];
        if (ch == '\\') {
            if (++i < keyPath.length()) {
                key.push_back(keyPath[i]);
                i++;
            } else {
                throw KeyPathError(keyPath, "Unescaped special character '\' found");
            }
        } else if (ch == ']') {
            throw KeyPathError(keyPath, "Unescaped special character ']' found");
        } else if (ch == '.' || ch == '[') {
            i--;
            break;
        } else {
            key.push_back(keyPath[i++]);
        }
    }
    if (key.length() == 0) {
        throw KeyPathError(keyPath, "Empty key found");
    }
    return make_pair(Path{key, nullopt}, i);
}

/** Parse array index starting from the giving startIndex. Return a pair of parsed result
 * in a pair of Path object and the end index of the array index (']') in the given keyPath. */
static pair<Path, size_t> parseArrayIndex(const string &keyPath, size_t startIndex) {
    string index;
    size_t i = startIndex;
    while (i < keyPath.length()) {
        auto ch = keyPath[i];
        if (isdigit(ch)) {
            index.push_back(ch);
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
        i++;
    }
    throw KeyPathError(keyPath, "Close bracket for an array index not found");
}

vector<Path> ts_support::keypath::parseKeyPath(const string &keyPath) {
    if (keyPath.length() == 0) {
        throw KeyPathError(keyPath, "Empty key path");
    }

    vector<Path> paths;
    size_t i = 0;
    while (i < keyPath.length()) {
        char ch = keyPath[i];
        if (i == 0) {
            if (ch == '$') { // Special '$.' prefix which indicates the beginning of the key path
                i++; // Skip '$'
                if (i < keyPath.length()) {
                    ch = keyPath[i];
                }
                if (ch != '.') {
                    throw KeyPathError(keyPath, "Prefix '$' is not followed by '.'");
                }
            }
        }

        if (ch == '.' || i == 0) {
            auto result = parseDictKey(keyPath, (ch == '.' ? i + 1 : i));
            paths.push_back(result.first);
            i = result.second + 1;
        } else if (ch == '[') {
            auto result = parseArrayIndex(keyPath, i + 1);
            paths.push_back(result.first);
            i = result.second + 1;
        } else {
            throw KeyPathError(keyPath, "Illegal character found at index " + to_string(i));
        }
    }
    return paths;
}