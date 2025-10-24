//
// test/keyPath.ts
//
// Copyright 2025-Present Couchbase, Inc.
//
// Use of this software is governed by the Business Source License included
// in the file licenses/BSL-Couchbase.txt.  As of the Change Date specified
// in that file, in accordance with the Business Source License, use of this
// software will be governed by the Apache License, Version 2.0, included in
// the file licenses/APL2.txt.
//

import type { CBLDictionary, CBLValue } from "@couchbase/lite-js";
import { HTTPError } from "./utils";

type KeyPathComponents = Array<string | number>;

/** JSONPath implementation that supports both "." properties and "[]" array indexes,
 *  and can both read and write object properties. */
export class KeyPath {
    constructor(readonly path: string) {
        function check(cond: boolean): asserts cond {
            if (!cond) throw new HTTPError(400, `Invalid KeyPath '${path}'`);
        }

        let str = path.trim();
        if (str.startsWith('$'))
            str = str.substring(1);
        else if (!str.startsWith('['))
            str = "." + str;

        let i = 0;
        while (i < str.length) {
            const m = str.substring(i).match(/\.([^.[]*)|\[(-?\d+)\]/);
            check(m !== null);
            if (m[0].startsWith('.')) {
                const key = m[1];
                check(key.length > 0);
                this.components.push(key);
            } else {
                const n = Number(m[2]);
                check(Number.isSafeInteger(n));
                this.components.push(n);
            }
            i += m[0].length;
        }

        this.str = str;
    }

    readonly components: KeyPathComponents = [];

    readonly str: string;

    /** Utility to create a KeyPath string from an array of path components. */
    static componentsToString(path: KeyPathComponents): string {
        if (path.length === 0) {
            return ".";
        } else {
            return path.flatMap( item => (typeof item === 'string') ? [".", item] : `[${item}]`)
                .join("");
        }
    }

    /** Returns the value at this path in `root`, else `undefined`. */
    read(root: CBLValue): CBLValue | undefined {
        let cur : CBLValue | undefined = root;
        for (const c of this.components) {
            if (typeof c === 'string')
                cur = isDictionary(cur) ? cur[c] : undefined;
            else
                cur = Array.isArray(cur) ? cur[c] : undefined;
            if (cur === undefined)
                break;
        }
        return cur;
    }

    /** Sets the value at this path in `root` to `value`, or deletes it if `value` is `undefined`.
     *  - If a key in the path refers to a non-existent object property, the key is added and
     *    set to an empty object or array; the traversal continues.
     *  - If an array index in the path is out of bounds, the array is padded with nulls until
     *    it is exactly large enough to make the specified index legal, and the specified index
     *    is set to an empty object or array; the traversal continues.
     *  - If a component of the path doesn't match the type of the actual value, i.e. the
     *    component is a scalar, or the component is a key but the value is an array, or vice
     *    versa, the traversal stops and the method returns false. */
    write(root: CBLValue, value: CBLValue | undefined): boolean {
        const makeCollection = (i: number) =>
            (typeof this.components[i] === 'string') ? {} : [];

        let cur : CBLValue = root;
        const last = this.components.length - 1;
        for (let i = 0; i <= last; ++i) {
            const c = this.components[i];
            if (typeof c === 'string') {
                if (!isDictionary(cur))
                    return false; // type mismatch
                if (i === last) {
                    if (value !== undefined)
                        cur[c] = value;
                    else
                        delete cur[c];
                } else if (c in cur) {
                    cur = cur[c];
                } else {
                    cur = cur[c] = makeCollection(i + 1);
                }

            } else {
                if (!Array.isArray(cur))
                    return false; // type mismatch
                if (i < last && cur.length >= c) {
                    cur = cur[c];
                } else {
                    while (cur.length < c)
                        cur.push(null); // pad the array if necessary
                    if (i === last) {
                        if (value !== undefined)
                            cur[c] = value;
                        else
                            cur.splice(c, 1);
                    } else {
                        cur = cur[c] = makeCollection(i + 1);
                    }
                }
            }
        }
        return true;
    }

    static read(root: CBLValue, path: string): CBLValue | undefined {
        return new KeyPath(path).read(root);
    }

    static write(root: CBLValue, path: string, value: CBLValue | undefined): boolean {
        return new KeyPath(path).write(root, value);
    }

    toString() {return this.str;}
}


/** A simple cache of precompiled KeyPaths. */
export class KeyPathCache {
    /** Turns a JSONPath string into a KeyPath. */
    path(str: string): KeyPath {
        let path = this.#paths.get(str);
        if (!path) {
            path = new KeyPath(str);
            this.#paths.set(str, path);
        }
        return path;
    }

    static path(str: string): KeyPath {
        if (!this.#sharedInstance)
            this.#sharedInstance = new KeyPathCache();
        return this.#sharedInstance.path(str);
    }

    #paths = new Map<string,KeyPath>();

    static #sharedInstance?: KeyPathCache;
}


function isDictionary(val: CBLValue | undefined) : val is CBLDictionary {
    return typeof val === "object" && val !== null && !Array.isArray(val) && !(val instanceof Blob);
}
