#include "CBLReplicationFilter.h"
#include "support/Define.h"
#include "support/JSON.h"

#include "cbl/CouchbaseLite.h"

#include <unordered_set>

using namespace std;

class DocumentIDsFilter : public ReplicationFilter {
public:
    explicit DocumentIDsFilter(const ReplicationFilterSpec &spec) : ReplicationFilter(spec) {
        auto params = ReplicationFilter::spec().params;
        _documentIDs = GetValue<unordered_set<string>>(params, "documentIDs");
    }

    bool run(CBLDocument *doc, unsigned int flags) override {
        auto ids = _documentIDs.find(STR(CBLDocument_ID(doc)));
        if (ids == _documentIDs.end()) {
            return false;
        }
        return true;
    }

    static string name() { return "documentIDs"; }

private:
    unordered_set<string> _documentIDs;
};

class DeletedDocumentsOnlyFilter : public ReplicationFilter {
public:
    explicit DeletedDocumentsOnlyFilter(const ReplicationFilterSpec &spec) : ReplicationFilter(spec) {}

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
