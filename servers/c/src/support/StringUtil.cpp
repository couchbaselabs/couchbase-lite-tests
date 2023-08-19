#include "StringUtil.h"

#include <sstream>

using namespace std;

namespace ts::support::str {
    vector <std::string> split(const string &str, char delimeter) {
        vector<std::string> elements;
        stringstream ss(str);
        string item;
        while (std::getline(ss, item, delimeter)) {
            elements.push_back(item);
        }
        return elements;
    }
}