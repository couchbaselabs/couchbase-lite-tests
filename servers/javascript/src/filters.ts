import type * as cbl from "@couchbase/lite-js";
import type * as tdk from "./tdkSchema";
import { check } from "./utils";


// https://github.com/couchbaselabs/couchbase-lite-tests/blob/main/spec/api/replication-filters.md

type ReplicatorFilter = (rev: cbl.RevisionInfo) => boolean;

type FilterMaker = (spec: tdk.Filter) => ReplicatorFilter;

export const TDKReplicationFilters: Record<string,FilterMaker> = {
    documentIDs: (spec) => {
        const documentIDs = spec.params?.documentIDs;
        check(Array.isArray(documentIDs), "invalid documentIDs in filter");
        const docSet = new Set(documentIDs);

        return rev => docSet.has(rev.id);
    },

    deletedDocumentsOnly: (_spec) => {
        return rev => !!rev.deleted;
    }
};


export function CreateFilter(filterSpec: tdk.Filter | undefined): ReplicatorFilter | undefined {
    if (!filterSpec) return undefined;
    const filterFn = TDKReplicationFilters[filterSpec.name]?.(filterSpec);
    check(filterFn !== undefined, `Unknown replicator filter "${filterSpec.name}"`);
    return filterFn;
}
