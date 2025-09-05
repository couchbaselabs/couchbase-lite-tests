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
        explicit LocalWinsConflictResolver(const ConflictResolverSpec &spec)
        : ConflictResolver(spec) {}

        const CBLDocument *
        resolve(const CBLDocument *localDoc, const CBLDocument *remoteDoc) override {
            return localDoc;
        }

        static string name() { return "local-wins"; }
    };

    class RemoteWinsConflictResolver : public ConflictResolver {
    public:
        explicit RemoteWinsConflictResolver(const ConflictResolverSpec &spec)
        : ConflictResolver(spec) {}

        const CBLDocument *
        resolve(const CBLDocument *localDoc, const CBLDocument *remoteDoc) override {
            return remoteDoc;
        }

        static string name() { return "remote-wins"; }
    };

    class DeleteConflictResolver : public ConflictResolver {
    public:
        explicit DeleteConflictResolver(const ConflictResolverSpec &spec)
        : ConflictResolver(spec) {}

        const CBLDocument *
        resolve(const CBLDocument *localDoc, const CBLDocument *remoteDoc) override {
            return nullptr;
        }

        static string name() { return "delete"; }
    };

    class MergeConflictResolver : public ConflictResolver {
    public:
        explicit MergeConflictResolver(const ConflictResolverSpec &spec)
        : ConflictResolver(spec)
        {
            auto params = ConflictResolver::spec().params;
            _property = GetValue<string>(params, "property");
        }

        const CBLDocument *
        resolve(const CBLDocument *localDoc, const CBLDocument *remoteDoc) override {
            if (!localDoc || !remoteDoc) { return nullptr; }

            auto mergedDoc = CBLDocument_MutableCopy(remoteDoc);
            auto mergedValues = FLMutableArray_New();

            FLSlice docKey = FLStr(_property.data());

            auto localProps = CBLDocument_Properties(localDoc);
            auto localValue = FLDict_Get(localProps, docKey);
            if (localValue) {
                FLMutableArray_AppendValue(mergedValues, localValue);
            } else {
                FLMutableArray_AppendNull(mergedValues);
            }

            auto remoteProps = CBLDocument_Properties(remoteDoc);
            auto remoteValue = FLDict_Get(remoteProps, docKey);
            if (remoteValue) {
                FLMutableArray_AppendValue(mergedValues, remoteValue);
            } else {
                FLMutableArray_AppendNull(mergedValues);
            }
            
            auto mergedProps = CBLDocument_MutableProperties(mergedDoc);
            FLMutableDict_SetArray(mergedProps, docKey, mergedValues);
            FLMutableArray_Release(mergedValues);
            return mergedDoc;
        }

        static string name() { return "merge"; }

    private:
        string _property;
    };

    class MergeDictConflictResolver : public ConflictResolver {
    public:
        explicit MergeDictConflictResolver(const ConflictResolverSpec &spec)
        : ConflictResolver(spec)
        {
            auto params = ConflictResolver::spec().params;
            _property = GetValue<string>(params, "property");
        }

        const CBLDocument *
        resolve(const CBLDocument *localDoc, const CBLDocument *remoteDoc) override {
            if (!localDoc || !remoteDoc) { return nullptr; }

            auto mergedDoc = CBLDocument_MutableCopy(remoteDoc);
            auto mergedProps = CBLDocument_MutableProperties(mergedDoc);

            FLSlice docKey = FLStr(_property.data());

            auto localProps = CBLDocument_Properties(localDoc);
            auto localDict = FLValue_AsDict(FLDict_Get(localProps, docKey)) ;

            auto remoteProps = CBLDocument_Properties(remoteDoc);
            auto remoteDict = FLValue_AsDict(FLDict_Get(remoteProps, docKey));

            if (!localDict || !remoteDict) {
                FLMutableDict_SetString(mergedProps, docKey, FLStr("Both values are not dictionary"));
                return mergedDoc;
            }

            auto mergedDict = FLMutableDict_New();

            // Merge Local:
            {
                FLDictIterator iter;
                FLDictIterator_Begin(localDict, &iter);
                FLValue value;
                while (nullptr != (value = FLDictIterator_GetValue(&iter))) {
                    FLString key = FLDictIterator_GetKeyString(&iter);
                    FLMutableDict_SetValue(mergedDict, key, value);
                    FLDictIterator_Next(&iter);
                }
            }

            // Merge Remote:
            {
                FLDictIterator iter;
                FLDictIterator_Begin(remoteDict, &iter);
                FLValue value;
                while (nullptr != (value = FLDictIterator_GetValue(&iter))) {
                    FLString key = FLDictIterator_GetKeyString(&iter);
                    FLMutableDict_SetValue(mergedDict, key, value);
                    FLDictIterator_Next(&iter);
                }
            }

            FLMutableDict_SetDict(mergedProps, docKey, mergedDict);
            FLMutableDict_Release(mergedDict);
            return mergedDoc;
        }

        static string name() { return "merge-dict"; }

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
        } else if (spec.name == MergeDictConflictResolver::name()) {
            return new MergeDictConflictResolver(spec);
        }
        return nullptr;
    }
}
