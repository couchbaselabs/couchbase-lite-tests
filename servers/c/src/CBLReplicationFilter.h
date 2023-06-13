#pragma once

#include <nlohmann/json.hpp>
#include <optional>
#include <string>

struct CBLDocument;

struct ReplicationFilterSpec {
    std::string name;
    nlohmann::json params;
};

class ReplicationFilter {
public:
    static ReplicationFilter *make_filter(const ReplicationFilterSpec &spec);

    explicit ReplicationFilter(const ReplicationFilterSpec &spec) : _spec(spec) {}

    virtual ~ReplicationFilter() = default;

    virtual bool run(CBLDocument *doc, unsigned flags) = 0;

protected:
    const ReplicationFilterSpec &spec() { return _spec; }

private:
    ReplicationFilterSpec _spec;
};
