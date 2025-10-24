//
// test/tdkSchema.ts
//
// Copyright 2025-Present Couchbase, Inc.
//
// Use of this software is governed by the Business Source License included
// in the file licenses/BSL-Couchbase.txt.  As of the Change Date specified
// in that file, in accordance with the Business Source License, use of this
// software will be governed by the Apache License, Version 2.0, included in
// the file licenses/APL2.txt.
//

import type { TestRequest } from "./testServer";
import type * as cbl from "@couchbase/lite-js";


// https://redocly.github.io/redoc/?url=https://raw.githubusercontent.com/couchbaselabs/couchbase-lite-tests/refs/heads/main/spec/api/api.yaml

export interface TDK {
    [GetInfoCommand](rq: TestRequest): Promise<GetInfoResponse>;
    [ResetCommand](rq: ResetRequest): Promise<void>;
    [GetAllDocumentsCommand](rq: GetAllDocumentsRequest): Promise<GetAllDocumentsResponse>;
    [GetDocumentCommand](rq: GetDocumentRequest): Promise<GetDocumentResponse>;
    [UpdateDatabaseCommand](rq: UpdateDatabaseRequest): Promise<void>;
    [StartReplicatorCommand](rq: StartReplicatorRequest): Promise<StartReplicatorResponse>;
    [StopReplicatorCommand](rq: StopReplicatorRequest): Promise<void>;
    [GetReplicatorStatusCommand](rq: GetReplicatorStatusRequest): Promise<GetReplicatorStatusResponse>;
    [SnapshotDocumentsCommand](rq: SnapshotDocumentsRequest): Promise<SnapshotDocumentsResponse>;
    [VerifyDocumentsCommand](rq: VerifyDocumentsRequest): Promise<VerifyDocumentsResponse>;
    [PerformMaintenanceCommand](rq: PerformMaintenanceRequest): Promise<void>;
    [NewSessionCommand](rq: NewSessionRequest): Promise<void>;
    [RunQueryCommand](rq: RunQueryRequest): Promise<RunQueryResponse>;
}


export const GetInfoCommand = "/";

export interface GetInfoResponse {
    version: string,
    apiVersion: number,
    cbl: "couchbase-lite-js",
    device: Record<string,string>,
    additionalInfo?: string,
}


export const ResetCommand = "/reset";

export interface ResetRequest extends TestRequest {
    databases: null | Record<string, {collections: string[] | undefined} | {dataset: string}>;
    test: string | undefined;
}


export const GetAllDocumentsCommand = "/getAllDocuments";

export interface GetAllDocumentsRequest extends TestRequest {
    database: string,
    collections: string[],
}

export type GetAllDocumentsResponse = Record<string, Array<{id:cbl.DocID, rev:cbl.RevID}>>;


export const GetDocumentCommand = "/getDocument";

export interface GetDocumentRequest extends TestRequest {
    database: string,
    document: {
        collection: string,
        id: cbl.DocID
    }
}

export type GetDocumentResponse = cbl.JSONObject & {
    _id: cbl.DocID,
    _revs: string,  // comma-delimited RevIDs
}


export const UpdateDatabaseCommand = "/updateDatabase";

export interface UpdateDatabaseRequest extends TestRequest {
    database: string,
    updates: DatabaseUpdateItem[],
}

export interface DatabaseUpdateItem {
    type: 'UPDATE' | 'DELETE' | 'PURGE',
    collection: string,
    documentID: cbl.DocID,
    updatedProperties?: cbl.JSONObject[],
    removedProperties?: string[],
    updatedBlobs?: Record<string,string>,
}


export const StartReplicatorCommand = "/startReplicator";

export interface StartReplicatorRequest extends TestRequest {
    config: {
        database: string,
        collections: ReplicatorCollection[],
        endpoint: string,
        replicatorType?: 'push' | 'pull' | 'pushAndPull',   // default is 'pushAndPull'
        continuous?: boolean,
        authenticator?: ReplicatorAuthenticator,
        enableDocumentListener?: boolean,
        enableAutoPurge?: boolean,                          // default is true
        headers?: Record<string,string>,
        pinnedServerCert?: string,
    },
    reset?: boolean,
}

export interface ReplicatorCollection {
    names: string[],
    channels?: string[],
    documentIDs?: cbl.DocID[],
    pushFilter?: Filter,
    pullFilter?: Filter,
    conflictResolver?: Filter,
}

export interface Filter {
    name: string,
    params?: cbl.JSONObject,
}

export interface ReplicatorAuthenticator {
    type: string,
}

export interface ReplicatorBasicAuthenticator extends ReplicatorAuthenticator {
    type: 'BASIC',
    username: string,
    password: string,
}

export interface ReplicatorSessionAuthenticator extends ReplicatorAuthenticator {
    type: 'SESSION',
    sessionID: string,
    cookieName: string,
}

export interface StartReplicatorResponse {
    id: string
}


export const StopReplicatorCommand = "/stopReplicator";

export interface StopReplicatorRequest extends TestRequest {
    id: string,
}


export const GetReplicatorStatusCommand = "/getReplicatorStatus";

export interface GetReplicatorStatusRequest extends TestRequest {
    id: string,
}

export interface GetReplicatorStatusResponse {
    activity: string,
    progress: {completed: boolean},
    documents?: DocumentReplication[],
    error?: ErrorInfo,
}

export interface DocumentReplication {
    collection: string,
    documentID: cbl.DocID,
    isPush?: boolean,
    flags?: Array<'deleted'>;   //TODO: other flags?
    error?: ErrorInfo
}

export interface ErrorInfo {
    domain: string,
    code: number,
    message: string,
}


export const SnapshotDocumentsCommand = "/snapshotDocuments";

export interface SnapshotDocumentsRequest extends TestRequest {
    database: string,
    documents: Array<{collection: string, id: cbl.DocID}>,
}

export interface SnapshotDocumentsResponse {
    id: string,
}


export const VerifyDocumentsCommand = "/verifyDocuments";

export interface VerifyDocumentsRequest extends TestRequest {
    database: string,
    snapshot: string,
    changes: DatabaseUpdateItem[],
}

export interface VerifyDocumentsResponse {
    result: boolean,
    description?: string,
    actual?: cbl.JSONValue,
    expected?: cbl.JSONValue,
    document?: cbl.CBLDocument | cbl.JSONObject,     // Document will stringify to an object
}


export const PerformMaintenanceCommand = "/performMaintenance";

export interface PerformMaintenanceRequest extends TestRequest {
    database: string,
    maintenanceType: 'compact' | 'integrityCheck' | 'optimize' | 'fullOptimize',
}


export const NewSessionCommand = "/newSession";

export interface NewSessionRequest extends TestRequest {
    id: string,
    logging?: {url: string, tag: string},
}


export const RunQueryCommand = "/runQuery";

export interface RunQueryRequest extends TestRequest {
    database: string,
    query: string,
}

export interface RunQueryResponse {
    results: cbl.JSONArray,
}


export const LogCommand = "/log";

export interface LogRequest extends TestRequest {
    message: string,
}



//-------- Loading datasets:

/** Base URL for our JSON datasets. */
export const kDatasetBaseURL = "https://raw.githubusercontent.com/couchbaselabs/couchbase-lite-tests/refs/heads/main/dataset/server/dbs/js/";
export const kBlobBaseURL = "https://media.githubusercontent.com/media/couchbaselabs/couchbase-lite-tests/refs/heads/main/dataset/server/blobs/js/";

/** Schema of `index.json` */
export interface DatasetIndex {
    name: string,
    collections: string[],
}

export type DatasetDoc = cbl.JSONObject & {
    _id: string,
}
