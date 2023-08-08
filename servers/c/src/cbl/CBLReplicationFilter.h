#pragma once

#include "nlohmann/json.hpp"
#include <optional>
#include <string>

struct CBLDocument;

namespace ts::cbl {
    struct ReplicationFilterSpec {
        std::string name;
        nlohmann::json params;
    };

    class ReplicationFilter {
    public:
        static ReplicationFilter *make_filter(const ReplicationFilterSpec &spec);

        explicit ReplicationFilter(ReplicationFilterSpec spec) : _spec(std::move(spec)) {}

        virtual ~ReplicationFilter() = default;

        virtual bool run(CBLDocument *doc, unsigned flags) = 0;

    protected:
        const ReplicationFilterSpec &spec() { return _spec; }

    private:
        ReplicationFilterSpec _spec;
    };
}
