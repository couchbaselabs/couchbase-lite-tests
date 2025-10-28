//
// snapshot.ts
//
// Copyright 2025-Present Couchbase, Inc.
//
// Use of this software is governed by the Business Source License included
// in the file licenses/BSL-Couchbase.txt.  As of the Change Date specified
// in that file, in accordance with the Business Source License, use of this
// software will be governed by the Apache License, Version 2.0, included in
// the file licenses/APL2.txt.
//

import { HTTPError, normalizeCollectionID } from "./utils";
import { KeyPath, KeyPathCache } from "./keyPath";
import type * as tdk from "./tdkSchema";
import type * as cbl from "@couchbase/lite-js";


export type BlobLoader = (blobURL: string) => Promise<cbl.NewBlob>;


/** Creates and verifies TDK database snapshots. */
export class Snapshot {
    constructor(readonly db: cbl.Database) { }

    /** Adds a (possibly nonexistent) document to the snapshot. */
    async record(collection: string, id: cbl.DocID) {
        const doc = await this.#getCollection(collection).getDocument(id);
        this.#documents.set(collection, id, doc ?? null);
    }


    /** Verifies the current database against the snapshot and a list of updates.
     *  @warning  This can only be called once, as it mutates the stored state. */
    async verify(changes: readonly tdk.DatabaseUpdateItem[],
                 blobLoader: BlobLoader): Promise<tdk.VerifyDocumentsResponse> {
        // Index the updates in a map for quick lookup:
        const updates = new DocumentMap<tdk.DatabaseUpdateItem>();
        for (const u of changes) {
            if (!this.#documents.get(u.collection, u.documentID) === undefined) {
                throw new HTTPError(400, `Update for unknown document ${u.documentID} in collection ${u.collection}`);
            }
            updates.set(u.collection, u.documentID, u);
        }

        // Now check each document in the snapshot:
        for (let [collection, id, oldDoc] of this.#documents) {
            const update = updates.get(collection, id);
            if (oldDoc || update) {
                let expected: cbl.CBLDocument | undefined;
                // Update the old document with the changes listed in the DatabaseUpdateItem:
                if (oldDoc) {
                    if (update)
                        expected = await this.#applyUpdate(oldDoc, update, blobLoader);
                    else
                        expected = oldDoc;
                } else {
                    oldDoc = this.#getCollection(collection).createDocument(id);
                    expected = await this.#applyUpdate(oldDoc, update!!, blobLoader);
                }
                // Compare the updated oldDoc against the database's current document:
                const newDoc = await this.#getCollection(collection).getDocument(id);
                const result = this.#compareDocs(expected, newDoc, update?.type);
                if (result !== undefined) {
                    // On failure, return the result:
                    result.result = false;
                    result.description = `Document ${id} in collection ${collection} ${result.description}`;
                    if (update?.type === "UPDATE") {
                        result.document = newDoc;
                    }
                    return result;
                }
            } else {
                // The doc should NOT exist; verify that:
                const foundDoc = await this.#getCollection(collection).getDocument(id);
                if (foundDoc) {
                    return {
                        result: false,
                        description: `Document ${id} in collection ${collection} should not exist`
                    };
                }
            }
        }
        return {result: true};
    }


    /** Applies the changes described in a `DatabaseUpdateItem` to a `CBLDocument`. */
    async #applyUpdate(doc: cbl.CBLDocument,
                       update: tdk.DatabaseUpdateItem,
                       blobLoader: BlobLoader) : Promise<cbl.CBLDocument | undefined>
    {
        if (update.type !== 'UPDATE')
            return undefined;

        const patch = (key: string, value: cbl.CBLValue | undefined) => {
            if (!KeyPathCache.path(key).write(doc, value))
                throw new HTTPError(400, `Type mismatch traversing path ${key}`);
        };

        if (update.updatedProperties !== undefined) {
            for (const updates of update.updatedProperties) {
                for (const key of Object.getOwnPropertyNames(updates))
                    patch(key,  updates[key]);
            }
        }
        if (update.removedProperties !== undefined) {
            for (const key of update.removedProperties)
                patch(key,  undefined);
        }
        if (update.updatedBlobs !== undefined) {
            for (const key of Object.getOwnPropertyNames(update.updatedBlobs))
                patch(key, await blobLoader(update.updatedBlobs[key]));
        }
        return doc;
    }


    /** Compares the expected and actual bodies of a document.
     *  @returns `undefined` if they're equal, or a response describing the mismatch. */
    #compareDocs(expected: cbl.CBLDocument | undefined,
                 actual: cbl.CBLDocument | undefined,
                 updateType: string | undefined) : tdk.VerifyDocumentsResponse | undefined {
        let response: tdk.VerifyDocumentsResponse | undefined = undefined;
        let path = new Array<string|number>();

        // Recursive comparison function; on error initializes `response` and returns false.
        const compare = (exp?: cbl.JSONValue, act?: cbl.JSONValue): boolean => {
            const fail = (): false => {
                response = {
                    result: false,
                    description: `had unexpected properties at ${KeyPath.componentsToString(path)}`,
                    actual: act,
                    expected: exp,
                };
                return false;
            };

            if (typeof exp !== typeof act) {
                // Type mismatch:
                return fail();
            }
            if (typeof exp !== 'object' || exp === null) {
                // Compare scalars:
                return exp === act || fail();
            } else if (Array.isArray(exp)) {
                if (!Array.isArray(act))
                    return fail();
                // Compare arrays:
                const expLen = Math.max(exp.length, act.length);
                for (let i = 0; i < expLen; ++i) {
                    path.push(i);
                    if (!compare(exp[i], act[i]))
                        return false;
                    path.pop();
                }
                return true;
            } else {
                if (Array.isArray(act))
                    return fail();
                // Compare objects:
                act = act as cbl.JSONObject;
                const expKeys = Object.keys(exp), actKeys = Object.keys(act);
                for (const key of expKeys) {
                    path.push(key);
                    if (!compare(exp[key], act[key]))
                        return false;
                    path.pop();
                }
                if (actKeys.length > expKeys.length) {
                    for (const key of actKeys) {
                        path.push(key);
                        if (!compare(exp[key], act[key]))
                            return false;
                        path.pop();
                    }
                }
                return true;
            }
        };

        if (expected) {
            if (actual) {
                compare(docToJSON(expected), docToJSON(actual));
            } else {
                response = {
                    result: false,
                    description: "was not found",
                };
            }
        } else {
            if (actual) {
                response = {
                    result: false,
                    description: "should not exist",
                };
                if (updateType === 'DELETE')
                    response.description = "was not deleted";
                else if (updateType === 'PURGE')
                    response.description = "was not purged";
            }
        }

        return response;
    }


    #getCollection(name: string): cbl.Collection {
        return this.db.getCollection(normalizeCollectionID(name));
    }


    readonly #documents = new DocumentMap<cbl.CBLDocument | null>();
}


/** A mapping from a collection ID and DocID to a type T. */
class DocumentMap<T> {
    set(collection: string, id: cbl.DocID, value: T | null) {
        let coll = this.#map.get(collection);
        if (coll === undefined) {
            coll = new Map<cbl.DocID, T>();
            this.#map.set(collection, coll);
        }
        coll.set(id, value);
    }

    get(collection: string, id: cbl.DocID): T | null | undefined {
        return this.#map.get(collection)?.get(id);
    }

    *[Symbol.iterator](): Generator<[string, cbl.DocID, T | null]> {
        for (const [collection, docs] of this.#map) {
            for (const [id, doc] of docs)
                yield [collection, id, doc];
        }
    }

    #map = new Map<string, Map<cbl.DocID, T | null>>();
}


/** Converts a CBLDocument to a regular JSON object (i.e. Blobs are replaced by their metadata.) */
function docToJSON(doc: cbl.CBLDocument): cbl.JSONObject {
    return JSON.parse(JSON.stringify(doc)) as cbl.JSONObject;
}
