//
// test/httpError.ts
//
// Copyright 2025-Present Couchbase, Inc.
//
// Use of this software is governed by the Business Source License included
// in the file licenses/BSL-Couchbase.txt.  As of the Change Date specified
// in that file, in accordance with the Business Source License, use of this
// software will be governed by the Apache License, Version 2.0, included in
// the file licenses/APL2.txt.
//

import type { CBLDictionary, CBLDocument, CBLValue, JSONObject, JSONValue } from "@couchbase/lite-js";
import { Blob } from "@couchbase/lite-js";


/** Test functions can throw this to report an HTTP error status. */
export class HTTPError extends Error {
    constructor(public readonly code: number, message?: string) {
        super(message);
        this.name = "HTTP";
    }
}


/** Simple assertion that throws an HTTPError with status 400 on failure. */
export function check(cond: boolean, message: string): asserts cond {
    if (!cond)
        throw new HTTPError(400, message);
}


/** Strips the default scope name from an incoming collection ID. */
export function normalizeCollectionID(id: string): string {
    return id.startsWith("_default.") ? id.substring(9) : id;
}


export function isObject(val: JSONValue | undefined) : val is JSONObject {
    return typeof val === "object" && val !== null && !Array.isArray(val);
}


export function isDict(val: CBLValue | undefined) : val is CBLDictionary {
    return typeof val === "object" && val !== null && !Array.isArray(val) && !(val instanceof Blob);
}


/** Converts a CBLDocument to a regular JSON object (i.e. Blobs are replaced by their metadata.) */
export function docToJSON(doc: CBLDocument): JSONObject {
    return JSON.parse(JSON.stringify(doc)) as JSONObject;
}
