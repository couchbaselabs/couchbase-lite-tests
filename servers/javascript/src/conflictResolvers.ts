import type * as cbl from "@couchbase/lite-js";
import type * as tdk from "./tdkSchema";
import { check, isDict } from "./utils";


// https://github.com/couchbaselabs/couchbase-lite-tests/blob/main/spec/api/conflict-resolvers.md

/* eslint-disable @typescript-eslint/require-await */

type ResolverMaker = (spec: tdk.Filter) => cbl.PullConflictResolver;

export const TDKConflictResolvers: Record<string,ResolverMaker> = {

    "local-wins": (_spec) => {
        return async (local, _remote) => local;
    },

    "remote-wins": (_spec) => {
        return async (_local, remote) => remote;
    },

    "delete": (_spec) => {
        return async (_local, _remote) => null;
    },

    "merge": (spec) => {
        const property = spec.params?.property;
        check(typeof property === 'string', "invalid conflict resolver parameter");

        return async (local, remote) => {
            if (local && remote) {
                const localProp = local[property] ?? null, remoteProp = remote[property] ?? null;
                local[property] = [ localProp, remoteProp ];
                return local;
            } else {
                return local ?? remote;
            }
        };
    },

    "merge-dict": (spec) => {
        const property = spec.params?.property;
        check(typeof property === 'string', "invalid conflict resolver parameter");

        return async (local, remote) => {
            if (local && remote) {
                const localDict = local[property], remoteDict = remote[property];
                let merged: cbl.CBLDictionary;
                if (isDict(localDict) && isDict(remoteDict)) {
                    merged = localDict;
                    for (const key of Object.getOwnPropertyNames(remoteDict)) {
                        if (key in merged) {
                            merged = {"error": `Conflicting values found at key named '${key}'`};
                            break;
                        }
                        merged[key] = remoteDict[key];
                    }
                } else {
                    merged = {"error": "Both values are not dictionary"};
                }
                local[property] = merged;
                return local;
            } else {
                return local ?? remote;
            }
        };
    },
};
