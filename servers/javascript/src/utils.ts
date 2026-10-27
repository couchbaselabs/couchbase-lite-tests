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
import { Blob, ReplicatorError } from "@couchbase/lite-js";
import type { ErrorInfo } from "./tdkSchema";

/** Test functions can throw this to report an HTTP error status. */
export class HTTPError extends Error {
    readonly domain = "TESTSERVER";

    constructor(
        public readonly code: number,
        message?: string,
    ) {
        super(message);
        this.name = "HTTP";
    }
}

/** Simple assertion that throws an HTTPError with status 400 on failure. */
export function check(cond: boolean, message: string): asserts cond {
    if (!cond) throw new HTTPError(400, message);
}

/** Strips the default scope name from an incoming collection ID. */
export function normalizeCollectionID(id: string): string {
    return id.startsWith("_default.") ? id.substring(9) : id;
}

export function isObject(val: JSONValue | undefined): val is JSONObject {
    return typeof val === "object" && val !== null && !Array.isArray(val);
}

export function isDict(val: CBLValue | undefined): val is CBLDictionary {
    return typeof val === "object" && val !== null && !Array.isArray(val) && !(val instanceof Blob);
}

/** Converts a CBLDocument to a regular JSON object (i.e. Blobs are replaced by their metadata.) */
export function docToJSON(doc: CBLDocument): JSONObject {
    return JSON.parse(JSON.stringify(doc)) as JSONObject;
}

/** Maps a CBL JS error onto the code a native test server would report for it. */
export function errorInfo(error: Error | undefined): ErrorInfo | undefined {
    if (!error) return undefined;

    // Native platforms report an HTTP or BLIP status, or a WebSocket close code, as CBL/10000+code.
    const code = serverCode(error);
    return code !== undefined && code > 0
        ? { domain: "CBL", code: code + 10000, message: error.message }
        : { domain: "CBL-JS", code: -1, message: error.message };
}

/** The HTTP or BLIP status, or WebSocket close code, that a CBL JS error carries. */
function serverCode(error: Error): number | undefined {
    if (error instanceof ReplicatorError) return error.code;
    // CBL JS does not export BLIPError or WebSocketError. A document's error is the unwrapped
    // BLIP reply to its "rev" message, for example a 403 for a rejected push.
    if ("blipErrorCode" in error) return error.blipErrorCode as number;
    if (error.name === "WebSocketError") {
        // The browser or CBL JS makes up 1000, 1005 and 1006 when the server sent no close code.
        const code = (error as Error & { code: number }).code;
        return [1000, 1005, 1006].includes(code) ? undefined : code;
    }
    return undefined;
}
