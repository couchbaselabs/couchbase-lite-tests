#include "UUID.h"
#include <random>
#include <sstream>

unsigned char randomChar() {
    std::random_device rd;
    std::mt19937 gen(rd());
    std::uniform_int_distribution<> dis(0, 255);
    return static_cast<unsigned char>(dis(gen));
}

std::string generateHex(const unsigned int num) {
    std::stringstream ss;
    for (auto i = 0u; i < num; i++) {
        const auto rc = randomChar();
        std::stringstream hexSs;
        hexSs << std::hex << int(rc);
        auto hex = hexSs.str();
        ss << (hex.length() < 2 ? '0' + hex : hex);
    }
    return ss.str();
}

std::string test_server_support::generateUUID() {
    std::stringstream ss;
    ss << generateHex(4) << '-'
       << generateHex(2) << '-'
       << generateHex(2) << '-'
       << generateHex(2) << '-'
       << generateHex(6);
    return ss.str();
}
