#pragma once

#include <string>
#include <unordered_map>

struct CBLDocument;

namespace ts::cbl {
    class Snapshot {
    public:
        Snapshot();

        ~Snapshot();

        std::string id() { return _id; }

        void
        putDocument(const std::string &collectionName, const std::string &documentID, const CBLDocument *document);

        const CBLDocument *document(const std::string &collectionName, const std::string &documentID);

    private:

        std::string _id;
        std::unordered_map<std::string, const CBLDocument *> _documents;
    };
}
