#pragma once
#include <string>
#include <vector>

struct mg_connection;
class Request;

class Dispatcher {
public:
    Dispatcher();

    int handle(mg_connection* conn) const;

private:
    using Handler = std::function<int(const Request& request)>;
    struct Rule {
        int version;
        std::string method;
        std::string path;
        Handler handler;
    };
    void addRule(const Rule& rule);

    [[nodiscard]] Handler findHandler(const Request& request) const;

    // Handler Functions:
    int handleGETRoot(const Request& request);

    // Member Variables:
    std::vector<Rule> _rules;
};
