#include "CBLReplicationConflictResolver.h"

// support
#include "CBLHeader.h"
#include CBL_HEADER(CouchbaseLite.h)

#include "JSON.h"

using namespace std;
using namespace ts::support::json_util;

namespace ts::cbl {
    class LocalWinsConflictResolver : public ConflictResolver {
    public:
        explicit LocalWinsConflictResolver(const ConflictResolverSpec &spec) : ConflictResolver(
            spec) {}

        const CBLDocument *
        resolve(const CBLDocument *localDoc, const CBLDocument *remoteDoc) override {
            return localDoc;
        }

        static string name() { return "local-wins"; }
    };

    class RemoteWinsConflictResolver : public ConflictResolver {
    public:
        explicit RemoteWinsConflictResolver(const ConflictResolverSpec &spec) : ConflictResolver(
            spec) {}

        const CBLDocument *
        resolve(const CBLDocument *localDoc, const CBLDocument *remoteDoc) override {
            return remoteDoc;
        }

        static string name() { return "remote-wins"; }
    };

    class DeleteConflictResolver : public ConflictResolver {
    public:
        explicit DeleteConflictResolver(const ConflictResolverSpec &spec) : ConflictResolver(
            spec) {}

        const CBLDocument *
        resolve(const CBLDocument *localDoc, const CBLDocument *remoteDoc) override {
            return nullptr;
        }

        static string name() { return "delete"; }
    };

    class MergeConflictResolver : public ConflictResolver {
    public:
        explicit MergeConflictResolver(const ConflictResolverSpec &spec) : ConflictResolver(
            spec) {
            auto params = ConflictResolver::spec().params;
            _property = GetValue<string>(params, "property");
        }

        const CBLDocument *
        resolve(const CBLDocument *localDoc, const CBLDocument *remoteDoc) override {
            if (!localDoc || !remoteDoc) { return nullptr; }

            auto doc = CBLDocument_MutableCopy(remoteDoc);

            FLSlice key = FLStr(_property.data());
            auto array = FLMutableArray_New();
            auto prop = CBLDocument_Properties(localDoc);
            auto value = FLDict_Get(prop, key);
            if (value) {
                FLMutableArray_AppendValue(array, value);
            } else {
                FLMutableArray_AppendNull(array);
            }

            prop = CBLDocument_Properties(remoteDoc);
            value = FLDict_Get(prop, key);
            if (value) {
                FLMutableArray_AppendValue(array, value);
            } else {
                FLMutableArray_AppendNull(array);
            }
            
            auto props = CBLDocument_MutableProperties(doc);
            FLMutableDict_SetArray(props, key, array);
            FLMutableArray_Release(array);

            return doc;
        }

        static string name() { return "merge"; }

    private:
        string _property;
    };

    ConflictResolver *ConflictResolver::make_resolver(const ConflictResolverSpec &spec) {
        if (spec.name == LocalWinsConflictResolver::name()) {
            return new LocalWinsConflictResolver(spec);
        } else if (spec.name == RemoteWinsConflictResolver::name()) {
            return new RemoteWinsConflictResolver(spec);
        } else if (spec.name == DeleteConflictResolver::name()) {
            return new DeleteConflictResolver(spec);
        } else if (spec.name == MergeConflictResolver::name()) {
            return new MergeConflictResolver(spec);
        }
        return nullptr;
    }
}
