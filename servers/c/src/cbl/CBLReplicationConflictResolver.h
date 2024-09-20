#pragma once

#include "nlohmann/json.hpp"
#include <optional>
#include <string>

struct CBLDocument;

namespace ts::cbl {
    struct ConflictResolverSpec {
        std::string name;
        nlohmann::json params;
    };

    class ConflictResolver {
    public:
        static ConflictResolver *make_resolver(const ConflictResolverSpec &spec);

        explicit ConflictResolver(ConflictResolverSpec spec) : _spec(std::move(spec)) {}

        virtual ~ConflictResolver() = default;

        virtual const CBLDocument *
        resolve(const CBLDocument *localDoc, const CBLDocument *remoteDoc) = 0;

    protected:
        const ConflictResolverSpec &spec() { return _spec; }

    private:
        ConflictResolverSpec _spec;
    };
}
