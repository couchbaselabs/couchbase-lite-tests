//
// test/tdk.ts
//
// Copyright 2025-Present Couchbase, Inc.
//
// Use of this software is governed by the Business Source License included
// in the file licenses/BSL-Couchbase.txt.  As of the Change Date specified
// in that file, in accordance with the Business Source License, use of this
// software will be governed by the Apache License, Version 2.0, included in
// the file licenses/APL2.txt.
//

/* eslint-disable @typescript-eslint/require-await */

import { KeyPathCache } from "./keyPath";
import { LogSlurpSender } from "./logSlurpSender";
import { check, HTTPError, normalizeCollectionID } from "./utils";
import { Snapshot } from "./snapshot";
import type { TestRequest } from "./testServer";
import * as tdk from "./tdkSchema";
import * as cbl from "@couchbase/lite-js";
import * as logtape from "@logtape/logtape";


interface ReplicatorInfo {
    replicator  : cbl.Replicator,
    documents?  : tdk.DocumentReplication[],
    finished    : boolean,
    error?      : Error,
}


export const APIVersion = 1;


/** Implementation of the TDK API, as a delegate object for TestServer. */
export class TDKImpl implements tdk.TDK, AsyncDisposable {

    async [Symbol.asyncDispose]() {
        await this.#closeDatabases();
        this.#logSender?.close();
        this.#logSender = undefined;
    }


    async #closeDatabases() {
        for (const [id, repl] of this.#replicators) {
            if (!repl.finished) {
                this.#logger.info `Reset: Stopping replicator ${id}`;
                repl.replicator.stop();
            }
        }
        this.#replicators.clear();

        for (const db of this.#databases.values()) {
            this.#logger.info `Reset: Closing database ${db.name}`;
            await db.closeAndDelete();
        }
        this.#databases.clear();
    }


    //////// NEW SESSION
    async [tdk.NewSessionCommand] (rq: tdk.NewSessionRequest): Promise<void> {
        check(this.#sessionID === undefined, "Can't start a second session");
        this.#sessionID = rq.id;
        if (rq.logging) {
            this.#logger.info `Connecting to LogSlurp at ${rq.logging.url} with id=${rq.id}, tag=${rq.logging.tag}`;
            this.#logSender = new LogSlurpSender(rq.logging.url, rq.id, rq.logging.tag);
            await this.#logSender.waitForConnected(5000);
        }
    }


    //////// GET INFO
    async [tdk.GetInfoCommand] (_rq: TestRequest): Promise<tdk.GetInfoResponse> {
        return {
            version: cbl.Version,
            apiVersion: APIVersion,
            cbl: "couchbase-lite-js",
            device: {
                "User-Agent": navigator.userAgent
            },
        };
    }


    //////// RESET
    async [tdk.ResetCommand] (rq: tdk.ResetRequest): Promise<void> {
        await this.#closeDatabases();
        if (rq.databases) {
            for (const name of Object.getOwnPropertyNames(rq.databases)) {
                const what = rq.databases[name];
                if ('dataset' in what)
                    await this.#loadDataset(name, what.dataset);
                else
                    await this.#createDatabase(name, what.collections);
            }
        }
        if (rq.test) {
            this.#logger.info(`>>>>>>>>>> ${rq.test}`);
        }
    }


    //////// GET ALL DOCUMENTS
    async [tdk.GetAllDocumentsCommand] (rq: tdk.GetAllDocumentsRequest): Promise<tdk.GetAllDocumentsResponse> {
        const db = this.#getDatabase(rq.database);
        const response: tdk.GetAllDocumentsResponse = {};
        for (const collName of rq.collections) {
            if (collName in db.collections) {
                const coll = db.getCollection(normalizeCollectionID(collName));
                const docs = new Array<{id:cbl.DocID, rev:cbl.RevID}>();
                response[collName] = docs;
                await coll.eachDocument( doc => {
                    const m = cbl.meta(doc);
                    docs.push({id: m.id, rev: m.revisionID!});
                    return true;
                });
            }
        }
        return response;
    }


    //////// GET DOCUMENT
    async [tdk.GetDocumentCommand] (rq: tdk.GetDocumentRequest): Promise<tdk.GetDocumentResponse> {
        const coll = this.#getDatabase(rq.database)
            .getCollection(normalizeCollectionID(rq.document.collection));
        const doc = await coll.getDocument(rq.document.id);
        if (!doc) throw new HTTPError(404, `No document "${rq.document.id}"`);
        const m = cbl.meta(doc);
        return {_id: rq.document.id, _revs: m.revisionID!};
    }


    //////// UPDATE DATABASE:
    async [tdk.UpdateDatabaseCommand] (rq: tdk.UpdateDatabaseRequest): Promise<void> {
        const db = this.#getDatabase(rq.database);
        await db.inTransaction("rw", db.collectionNames, async () => {
            for (const update of rq.updates) {
                const coll = db.getCollection(normalizeCollectionID(update.collection));
                let doc = await coll.getDocument(update.documentID);
                if (!doc) {
                    doc = coll.createDocument(update.documentID);
                    await coll.save(doc);
                }

                const updatePath = (pathStr: string, value: cbl.CBLValue | undefined): void => {
                    if (!KeyPathCache.path(pathStr).write(doc, value))
                        throw new HTTPError(400, `Invalid path ${pathStr} in doc ${update.documentID}`);
                };

                switch (update.type) {
                    case 'UPDATE': {
                        if (update.updatedProperties) {
                            for (const props of update.updatedProperties) {
                                for (const pathStr of Object.getOwnPropertyNames(props))
                                    updatePath(pathStr, props[pathStr]);
                            }
                        }
                        if (update.removedProperties) {
                            for (const props of update.removedProperties) {
                                updatePath(props, undefined);
                            }
                        }
                        if (update.updatedBlobs) {
                            for (const pathStr of Object.getOwnPropertyNames(update.updatedBlobs)) {
                                const blob = await this.#downloadBlob(update.updatedBlobs[pathStr]);
                                updatePath(pathStr, blob);
                            }
                        }
                        await coll.save(doc);
                        break;
                    }
                    case 'DELETE':
                        await coll.delete(doc);
                        break;
                    case 'PURGE':
                        await coll.purge(doc);
                        break;
                }
            }
        });
    }


    //////// START REPLICATOR:
    async [tdk.StartReplicatorCommand] (rq: tdk.StartReplicatorRequest): Promise<tdk.StartReplicatorResponse> {
        const db = this.#getDatabase(rq.config.database);
        const config: cbl.ReplicatorConfig = {
            database:    db,
            url:         rq.config.endpoint,
            collections: {},
        };
        if (rq.config.authenticator) {
            if (rq.config.authenticator.type !== 'BASIC')
                throw new HTTPError(501, "Only Basic auth is supported");
            const basicAuth = rq.config.authenticator as tdk.ReplicatorBasicAuthenticator;
            config.credentials = {
                username: basicAuth.username,
                password: basicAuth.password
            };
        }
        for (const colls of rq.config.collections) {
            if (colls.documentIDs || colls.pushFilter || colls.pullFilter || colls.conflictResolver)
                throw new HTTPError(501, "Unimplemented replication feature(s)");
            const collCfg: cbl.ReplicatorCollectionConfig = { };
            if (rq.config.replicatorType !== 'pull') {
                if (colls.pushFilter) throw new HTTPError(501, "Push filter is not supported");
                collCfg.push = {
                    continuous: rq.config.continuous,
                    //filter: colls.pushFilter                  //TODO
                };
            }
            if (rq.config.replicatorType !== 'push') {
                if (colls.pullFilter)
                    throw new HTTPError(501, "Pull filter is not supported");
                if (colls.documentIDs)
                    throw new HTTPError(501, "List of docIDs is not supported");
                if (colls.conflictResolver)
                    throw new HTTPError(501, "Conflict resolver is not supported");
                collCfg.pull = {
                    continuous: rq.config.continuous,
                    channels:   colls.channels,
                    //documentIDs: colls.documentIDs,           //FIXME
                    //filter: colls.pullFilter,                 //TODO
                    //conflictResolver: colls.conflictResolver, //TODO
                };
            }
            for (const collName of colls.names)
                config.collections[collName] = collCfg;
        }

        const repl = new cbl.Replicator(config);
        const info: ReplicatorInfo = {replicator: repl, documents: [], finished: false};

        if (rq.config.enableDocumentListener) {
            repl.onDocuments = (collection, direction, documents) => {
                if (info.documents === undefined)
                    info.documents = [];
                for (const doc of documents) {
                    info.documents.push({
                        collection: collectionIDWithScope(collection.name),
                        documentID: doc.docID,
                        isPush:     (direction === 'push'),
                        flags:      (doc.deleted ? ["deleted"] : undefined),
                        error:      this.#mkErrorInfo(doc.error),
                    });
                }
            };
        }

        const id = `repl-${++this.#idCounter}`;
        this.#replicators.set(id, info);
        repl.run().then(
            _ok   => {info.finished = true;},
            error => {info.finished = true; info.error = error as Error;}
        );
        return {id};
    }


    //////// STOP REPLICATOR:
    async [tdk.StopReplicatorCommand] (rq: tdk.StopReplicatorRequest): Promise<void> {
        const info = this.#replicators.get(rq.id);
        if (!info)
            throw new HTTPError(404, `No replicator with ID "${rq.id}"`);
        info.replicator.stop();
    }


    //////// REPLICATOR STATUS:
    async [tdk.GetReplicatorStatusCommand] (rq: tdk.GetReplicatorStatusRequest): Promise<tdk.GetReplicatorStatusResponse> {
        const info = this.#replicators.get(rq.id);
        if (!info)
            throw new HTTPError(404, `No replicator with ID "${rq.id}"`);
        const status = info.replicator.status;
        const documents = info.documents;
        info.documents = undefined;

        return {
            activity:   status.status?.toUpperCase() ?? "STOPPED",
            progress:   { completed: (status.status === 'stopped') },
            documents:  documents,
            error:      this.#mkErrorInfo(info.error),
        };
    }


    //////// RUN QUERY:
    async [tdk.RunQueryCommand] (rq: tdk.RunQueryRequest): Promise<tdk.RunQueryResponse> {
        const db = this.#getDatabase(rq.database);
        const rows = await db.createQuery(rq.query).execute();
        return {
            results: rows
        };
    }


    //////// PERFORM MAINTENANCE:
    async [tdk.PerformMaintenanceCommand] (rq: tdk.PerformMaintenanceRequest): Promise<void> {
        const db = this.#getDatabase(rq.database);
        switch (rq.maintenanceType) {
            case 'compact':
                await db.performMaintenance('compact');
                break;
            default:
                throw new HTTPError(501, "Unimplemented maintenance type");
        }
    }


    //////// SNAPSHOT DOCUMENTS:
    async [tdk.SnapshotDocumentsCommand] (rq: tdk.SnapshotDocumentsRequest): Promise<tdk.SnapshotDocumentsResponse> {
        const db = this.#getDatabase(rq.database);
        const snap = new Snapshot(db);
        for (const d of rq.documents)
            await snap.record(d.collection, d.id);
        const snapID = `snap-${++this.#snapshotCounter}`;
        this.#snapshots.set(snapID, snap);
        return {id: snapID};
    }


    //////// VERIFY DOCUMENTS:
    async [tdk.VerifyDocumentsCommand] (rq: tdk.VerifyDocumentsRequest): Promise<tdk.VerifyDocumentsResponse> {
        const db = this.#getDatabase(rq.database);
        const snap = this.#snapshots.get(rq.snapshot);
        if (snap === undefined)
            throw new HTTPError(404, `No such snapshot ${rq.snapshot}`);
        if (snap.db !== db)
            throw new HTTPError(400, `Snapshot is of a different database, ${db.name}`);
        this.#snapshots.delete(rq.snapshot);

        return await snap.verify(rq.changes);
    }


    //-------- Internals:


    #mkErrorInfo(error: Error | undefined): tdk.ErrorInfo | undefined {
        return error ? {domain: "CBL-JS", code: -1, message: error.message} : undefined;
    }


    #getDatabase(name: string): cbl.Database {
        const db = this.#databases.get(name);
        if (!db) throw new HTTPError(400, `No open database "${name}"`);
        return db;
    }


    async #createDatabase(name: string, collections: readonly string[] | undefined): Promise<cbl.Database> {
        check(!this.#databases.has(name), `There is already an open database named ${name}`);
        let colls: Record<string,cbl.CollectionConfig> = {};
        if (collections) {
            for (const coll of collections)
                colls[coll] = {};
        }
        this.#logger.info `Reset: Creating database ${name} with ${collections?.length ?? 0} collection(s)`;
        const db = await cbl.Database.open({name: name, version: 1, collections: colls});
        this.#databases.set(name, db);
        return db;
    }


    async #loadDataset(dbName: string, datasetName: string) {
        const url = tdk.kDatasetBaseURL + datasetName + "/";

        const fetchRelative = async (suffix: string): Promise<string> => {
            const response = await fetch(url + suffix);
            if (response.status !== 200)
                throw new HTTPError(502, `Unable to load dataset <${url + suffix}>: ${response.status} ${response.statusText}`);
            return await response.text();
        };

        this.#logger.info `Loading database ${dbName} from dataset ${datasetName} at ${url} ...`;
        const config = JSON.parse(await fetchRelative("index.json")) as tdk.DatasetIndex;
        if (typeof config.name !== 'string' || !Array.isArray(config.collections))
            throw new HTTPError(400, `Not a valid dataset index at <${url}index.json>`);

        const db = await this.#createDatabase(dbName, config.collections);

        let totalDocs = 0, totalBlobs = 0;
        for (const collID of config.collections) {
            this.#logger.debug `- Loading docs in collection ${collID}...`;
            const collection = db.getCollection(normalizeCollectionID(collID));
            const docs: cbl.CBLDocument[] = [];
            const jsonl = await fetchRelative(`${collID}.jsonl`);
            for (const line of jsonl.trim().split('\n')) {
                if (line.trim().length > 0) {
                    const doc = JSON.parse(line) as tdk.DatasetDoc;
                    const id = cbl.DocID(doc._id);
                    const body: cbl.JSONObject = doc;
                    delete body['_id'];

                    // Search for blobs and download the data:
                    totalBlobs += await this.#installBlobs(body, url);

                    docs.push(collection.createDocument(id, body));
                }
            }
            await collection.updateMultiple({save: docs});
            this.#logger.info `- Added ${docs.length} docs to collection ${collID}...`;
            totalDocs += docs.length;
        }
        this.#logger.info `Finished creating database ${dbName} with ${totalDocs} docs and ${totalBlobs} blobs.`;
    }


    async #installBlobs(doc: cbl.JSONObject, datasetURL: string): Promise<number> {
        let totalBlobs = 0;
        const _installBlobs = async (obj: cbl.CBLValue) : Promise<cbl.NewBlob | undefined> =>{
            if (Array.isArray(obj)) {
                let i = 0;
                for (const v of obj) {
                    const blob = await _installBlobs(v);  // recurse
                    if (blob)
                        obj[i] = blob;
                    ++i;
                }
            } else if (typeof obj === 'object' && obj !== null) {
                obj = obj as cbl.CBLDictionary;
                if (obj["@type"] === "blob" && typeof obj.digest === "string") {
                    ++totalBlobs;
                    return await this.#downloadDataSetBlob(obj as unknown as cbl.Bloblike, datasetURL);
                }
                for (const key of Object.getOwnPropertyNames(obj)) {
                    const blob = await _installBlobs(obj[key]);  // recurse
                    if (blob)
                        obj[key] = blob;
                }
            }
            return undefined;
        };
        await _installBlobs(doc);
        return totalBlobs;
    }


    async #downloadDataSetBlob(blobMeta: cbl.Bloblike, datasetURL: string): Promise<cbl.NewBlob> {
        check(blobMeta.digest.startsWith("sha1-"), "Unexpected prefix in blob digest");
        const digest = blobMeta.digest.substring(5).replaceAll('/', '_');
        const blobURL = `${datasetURL}Attachments/${digest}.blob`;
        this.#logger.info `  - downloading blob ${blobMeta.digest}`;
        const contents = await this.#downloadBlobContents(blobURL);
        return new cbl.NewBlob(contents, blobMeta.content_type);
    }


    async #downloadBlob(blobURL: string): Promise<cbl.NewBlob> {
        if (blobURL.endsWith(".zip"))
            throw new HTTPError(501, "Unzipping blobs is not supported");
        const contents = await this.#downloadBlobContents(blobURL);
        const type = blobURL.endsWith(".jpg") ? "image/jpeg" : "application/octet-stream";
        return new cbl.NewBlob(contents, type);
    }


    async #downloadBlobContents(blobURL: string): Promise<Uint8Array> {
        const response = await fetch(blobURL);
        if (response.status !== 200)
            throw new HTTPError(502, `Unable to load blob from <${blobURL}>: ${response.status} ${response.statusText}`);
        const data = await response.arrayBuffer();
        return new Uint8Array(data);
    }


    readonly #databases     = new Map<string,cbl.Database>();
    readonly #replicators   = new Map<string,ReplicatorInfo>();
    readonly #snapshots     = new Map<string,Snapshot>();
    readonly #logger        = logtape.getLogger("TDK");
    #idCounter              = 0;
    #snapshotCounter        = 0;
    #sessionID?             : string;
    #logSender?             : LogSlurpSender;
}

/** Adds the default scope name, if necessary, to an outgoing collection ID. */
function collectionIDWithScope(id: string): string {
    return id.includes('.') ? id : `_default.${id}`;
}
