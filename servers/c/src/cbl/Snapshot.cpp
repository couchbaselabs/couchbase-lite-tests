#include "Snapshot.h"

// cbl
#include "CBLHeader.h"
#include CBL_HEADER(CBLDocument.h)

// support
#include "UUID.h"

// lib
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

    const CBLDocument *Snapshot::document(const string &collectionName, const string &docID) {
        auto key = collectionName + "." + docID;
        if (_documents.find(key) == _documents.end()) {
            throw logic_error("Document was not snapped shot : " + key);
        }
        return _documents[key];
    }
}
