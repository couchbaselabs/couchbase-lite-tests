#include "Snapshot.h"

// cbl
#include "CBLHeader.h"
#include CBL_HEADER(CBLDocument.h)

// support
#include "StringUtil.h"
#include "UUID.h"

// lib
#include <assert.h>
#include <stdexcept>

using namespace std;
using namespace ts::support;

namespace ts::cbl {
    Snapshot::Snapshot() {
        _id = key::generateUUID();
    }

    Snapshot::~Snapshot() {
        for (const auto &doc: _documents) {
            CBLDocument_Release(doc.second);
        }
        _documents.clear();
    }

    void Snapshot::putDocument(const string &collectionName, const string &docID, const CBLDocument *doc) {
        // Note: document could be NULL
        CBLDocument_Retain(doc);
        _documents[collectionName + "." + docID] = doc;
    }

    const CBLDocument *Snapshot::document(const string &colName, const string &docID, bool mustExist) {
        auto key = documentKey(colName, docID);
        if (_documents.find(key) == _documents.end()) {
            if (mustExist) {
                throw logic_error(str::concat("Document '", key, "' was not in the snapshot"));
            }
            return nullptr;
        }
        return _documents[key];
    }

    std::unordered_map<std::string, const CBLDocument *> Snapshot::allDocuments() {
        return _documents;
    }

    std::string Snapshot::documentKey(const std::string &colName, const std::string &docID) {
        return str::concat(colName, ".", docID);
    }

    std::pair<std::string, std::string> Snapshot::documentKeyComponents(const std::string &documentKey) {
        auto elements = str::split(documentKey, '.');
        assert(elements.size() == 3);
        return make_pair(str::concat(elements[0], ".", elements[1]), elements[2]);
    }
}
