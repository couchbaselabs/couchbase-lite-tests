#pragma once

#include <nlohmann/json.hpp>
#include <string>
#include <unordered_map>
#include <vector>

struct mg_connection;

class Dispatcher {
public:
    Dispatcher();

    int handle(mg_connection* conn);

private:
    using Handler = std::function<void(nlohmann::json&, mg_connection*)>;

    struct Rule {
        int version;
        std::string method;
        std::string path;
        Handler handler;
    };

    void addHandler(int version, std::string method, std::string path, const Handler& handler);
    Handler findHandler(int version, std::string method, const std::string& path);

    int sendErrorCode(mg_connection* conn, int code, const std::string& message = "");
    void sendJSONResponse(mg_connection* conn, const nlohmann::json& object);

    void handleGetRoot(nlohmann::json&, mg_connection*);

    std::vector<Rule> _rules;
};
