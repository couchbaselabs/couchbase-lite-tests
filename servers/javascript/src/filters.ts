import * as cbl from "@couchbase/lite-js";

import type * as tdk from "./tdkSchema";
import {check, isObject} from "./utils";

// https://github.com/couchbaselabs/couchbase-lite-tests/blob/main/spec/api/replication-filters.md

type PushReplicatorFilter = (doc: cbl.CBLDocument, flags: cbl.DocumentFlags) => boolean;
type PushFilterMaker = (spec: tdk.Filter) => PushReplicatorFilter;
type PullReplicatorFilter = (doc: cbl.CBLDocument, flags: cbl.DocumentFlags) => boolean;
type PullFilterMaker = (spec: tdk.Filter) => PullReplicatorFilter;

function _documentIDs(spec: tdk.Filter, doc: cbl.CBLDocument, _flags: cbl.DocumentFlags) : boolean {
    const documentIDs = spec.params?.documentIDs;
    check(isObject(documentIDs), "documentIDs must be an object");

    const meta = cbl.meta(doc);
    const ids = documentIDs[meta.collection.name];
    check(Array.isArray(ids), "documentIDs's value must be an array");

    const docSet = new Set(ids);
    return docSet.has(meta.id);
}

function _deletedDocumentsOnly(_doc: cbl.CBLDocument, flags: cbl.DocumentFlags) : boolean {
    return (flags & cbl.DocumentFlags.deleted) !== 0;
}

export const TDKPushReplicationFilters: Record<string,PushFilterMaker> = {
    documentIDs: (spec) => {
        return (doc, flags) => _documentIDs(spec, doc, flags);
    },

    deletedDocumentsOnly: (_spec) => {
        return (doc, flags) => _deletedDocumentsOnly(doc, flags);
    }
};

export const TDKPullReplicationFilters: Record<string,PullFilterMaker> = {
    documentIDs: (spec) => {
        return (doc, flags) => _documentIDs(spec, doc, flags);
    },

    deletedDocumentsOnly: (_spec) => {
        return (doc, flags) => _deletedDocumentsOnly(doc, flags);
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
