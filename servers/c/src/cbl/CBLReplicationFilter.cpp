#include "CBLReplicationFilter.h"

// support
#include "CBLHeader.h"
#include CBL_HEADER(CouchbaseLite.h)

#include "CollectionSpec.h"
#include "Define.h"
#include "JSON.h"

// lib
#include <unordered_map>
#include <vector>

using namespace std;
using namespace ts::support::json_util;

namespace ts::cbl {
    class DocumentIDsFilter : public ReplicationFilter {
    public:
        explicit DocumentIDsFilter(const ReplicationFilterSpec &spec) : ReplicationFilter(spec) {
            auto params = ReplicationFilter::spec().params;
            _documentIDs = GetValue<unordered_map<string, vector<string>>>(params, "documentIDs");
        }

        bool run(CBLDocument *doc, unsigned int flags) override {
            auto collectionName = CollectionSpec(CBLDocument_Collection(doc)).fullName();
            auto ids = _documentIDs[collectionName];
            if (std::find(ids.begin(), ids.end(), STR(CBLDocument_ID(doc))) == ids.end()) {
                return false;
            }
            return true;
        }

        static string name() { return "documentIDs"; }

    private:
        unordered_map <string, vector<string>> _documentIDs;
    };

    class DeletedDocumentsOnlyFilter : public ReplicationFilter {
    public:
        explicit DeletedDocumentsOnlyFilter(const ReplicationFilterSpec &spec) : ReplicationFilter(
            spec) {}

        bool run(CBLDocument *doc, unsigned int flags) override {
            return flags == kCBLDocumentFlagsDeleted;
        }

        static string name() { return "deletedDocumentsOnly"; }
    };

    ReplicationFilter *ReplicationFilter::make_filter(const ReplicationFilterSpec &spec) {
        if (spec.name == DocumentIDsFilter::name()) {
            return new DocumentIDsFilter(spec);
        } else if (spec.name == DeletedDocumentsOnlyFilter::name()) {
            return new DeletedDocumentsOnlyFilter(spec);
        }
        return nullptr;
    }
}
