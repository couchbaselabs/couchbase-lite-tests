import * as cbl from "@couchbase/lite-js";

import type * as tdk from "./tdkSchema";
import {check, isObject} from "./utils";

// https://github.com/couchbaselabs/couchbase-lite-tests/blob/main/spec/api/replication-filters.md

type ReplicatorFilter = (doc: cbl.CBLDocument, flags: cbl.DocumentFlags) => boolean;
type FilterMaker = (spec: tdk.Filter) => ReplicatorFilter;

export const TDKReplicationFilters: Record<string,FilterMaker> = {
    documentIDs: (spec) => {
        return (doc, _) => {
            const documentIDs = spec.params?.documentIDs;
            check(isObject(documentIDs), "documentIDs must be an object");

            const meta = cbl.meta(doc);
            const ids = documentIDs[meta.collection.name];
            check(Array.isArray(ids), "documentIDs's value must be an array");

            const docSet = new Set(ids);
            return docSet.has(meta.id);
        };
    },

    deletedDocumentsOnly: (_spec) => {
        return (_, flags) => (flags & cbl.DocumentFlags.deleted) !== 0;
    }
};

export function CreateFilter(filterSpec: tdk.Filter | undefined): ReplicatorFilter | undefined {
    if (!filterSpec) return undefined;
    const filterFn = TDKReplicationFilters[filterSpec.name]?.(filterSpec);
    check(filterFn !== undefined, `Unknown replicator filter "${filterSpec.name}"`);
    return filterFn;
}
