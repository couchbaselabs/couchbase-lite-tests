#include "StringUtil.h"

#include <cctype>
#include <sstream>
#include <algorithm>

using namespace std;

namespace ts::support::str {
    vector <string> split(const string &str, char delimeter) {
        vector<string> elements;
        stringstream ss(str);
        string item;
        while (getline(ss, item, delimeter)) {
            elements.push_back(item);
        }
        return elements;
    }

    string tolower(const string &str) {
        auto val = str;
        transform(val.begin(), val.end(), val.begin(), [](unsigned char c) { return std::tolower(c); });
        return val;
    }
}