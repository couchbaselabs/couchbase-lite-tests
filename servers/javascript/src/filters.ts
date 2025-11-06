import type * as cbl from "@couchbase/lite-js";
import type * as tdk from "./tdkSchema";
import {check, isObject} from "./utils";


// https://github.com/couchbaselabs/couchbase-lite-tests/blob/main/spec/api/replication-filters.md

type PushReplicatorFilter = (rev: cbl.RevisionInfo) => boolean;
type PushFilterMaker = (spec: tdk.Filter) => PushReplicatorFilter;
type PullReplicatorFilter = (rev: cbl.RemoteRevisionInfo) => boolean;
type PullFilterMaker = (spec: tdk.Filter) => PullReplicatorFilter;

function _documentIDs(spec: tdk.Filter, rev: cbl.RemoteRevisionInfo | cbl.RevisionInfo) : boolean {
    const documentIDs = spec.params?.documentIDs;
    check(isObject(documentIDs), "documentIDs must be an object");
    // Currently JS API doesn't provide information regarding the collection
    // so validating that only one collection is allowed at least for now.
    check(Object.keys(documentIDs).length === 1, "documentIDs have more than one collection");

    const ids = Object.values(documentIDs)[0];
    check(Array.isArray(ids), "documentIDs's value must be an array");

    const docSet = new Set(ids);
    return docSet.has(rev.id as string);
}

function _deletedDocumentsOnly(rev: cbl.RemoteRevisionInfo | cbl.RevisionInfo) : boolean {
    return !!rev.deleted;
}

export const TDKPushReplicationFilters: Record<string,PushFilterMaker> = {
    documentIDs: (spec) => {
        return rev => _documentIDs(spec, rev);
    },

    deletedDocumentsOnly: (_spec) => {
        return rev => _deletedDocumentsOnly(rev);
    }
};

export const TDKPullReplicationFilters: Record<string,PullFilterMaker> = {
    documentIDs: (spec) => {
        return rev => _documentIDs(spec, rev);
    },

    deletedDocumentsOnly: (_spec) => {
        return rev => _deletedDocumentsOnly(rev);
    }
};

export function CreatePushFilter(filterSpec: tdk.Filter | undefined): PushReplicatorFilter | undefined {
    if (!filterSpec) return undefined;
    const filterFn = TDKPushReplicationFilters[filterSpec.name]?.(filterSpec);
    check(filterFn !== undefined, `Unknown replicator filter "${filterSpec.name}"`);
    return filterFn;
}

export function CreatePullFilter(filterSpec: tdk.Filter | undefined): PullReplicatorFilter | undefined {
    if (!filterSpec) return undefined;
    const filterFn = TDKPullReplicationFilters[filterSpec.name]?.(filterSpec);
    check(filterFn !== undefined, `Unknown replicator filter "${filterSpec.name}"`);
    return filterFn;
}
