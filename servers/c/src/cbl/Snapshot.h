#pragma once

#include <string>
#include <unordered_map>
#include <vector>

struct CBLDocument;

namespace ts::cbl {
    class Snapshot {
    public:
        Snapshot();

        ~Snapshot();

        /** Get the snapshot ID. */
        std::string id() { return _id; }

        /** Put a document into the snapshot. */
        void putDocument(const std::string &colName, const std::string &docID, const CBLDocument *doc);

        /** Get the document from the snapshot.
         *  If the document doesn't exist, exception will be raised if mustExist = true, otherwise
         *  NULL is returned. */
        const CBLDocument *document(const std::string &colName, const std::string &docID, bool mustExist);

        /** Get all documents in the snapshot as a map of document key and document */
        std::unordered_map<std::string, const CBLDocument *> allDocuments();

        /** Construct document key. */
        static std::string documentKey(const std::string &colName, const std::string &docID);

        /* Return a pair of <collection name, document id> from the given document key */
        static std::pair<std::string, std::string> documentKeyComponents(const std::string &documentKey);

    private:
        std::string _id;
        std::unordered_map<std::string, const CBLDocument *> _documents;
    };
}
