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


/** Test functions can throw this to report an HTTP error status. */
export class HTTPError extends Error {
    constructor(public readonly code: number, message?: string) {
        super(message);
        this.name = "HTTP";
    }
}

export function check(cond: boolean, message: string): asserts cond {
    if (!cond)
        throw new HTTPError(400, message);
}
