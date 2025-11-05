import type * as cbl from "@couchbase/lite-js";
import type * as tdk from "./tdkSchema";
import {check, isObject} from "./utils";


// https://github.com/couchbaselabs/couchbase-lite-tests/blob/main/spec/api/conflict-resolvers.md

/* eslint-disable @typescript-eslint/require-await */

type ResolverMaker = (spec: tdk.Filter) => cbl.PullConflictResolver;

export const TDKConflictResolvers: Record<string,ResolverMaker> = {

    "local-wins": (_spec) => {
        return async (_collection, local, _remote) => local;
    },

    "remote-wins": (_spec) => {
        return async (_collection, _local, remote) => remote;
    },

    "delete": (_spec) => {
        return async (_collection, local, _remote) => {
            return { ...local, deleted: 1, body: {} };
        };
    },

    "merge": (spec) => {
        const property = spec.params?.property;
        check(typeof property === 'string', "invalid conflict resolver parameter");

        return async (_collection, local, remote) => {
            if (!local.deleted && !remote.deleted) {
                const localProp = local.body[property] ?? null, remoteProp = remote.body[property] ?? null;
                local.body[property] = [ localProp, remoteProp ];
                return local;
            } else {
                return local.deleted ? local : remote;
            }
        };
    },

    "merge-dict": (spec) => {
        const property = spec.params?.property;
        check(typeof property === 'string', "invalid conflict resolver parameter");

        return async (_collection, local, remote) => {
            if (!local.deleted && !remote.deleted) {
                const localDict = local.body[property], remoteDict = remote.body[property];
                let merged: cbl.JSONObject;
                if (isObject(localDict) && isObject(remoteDict)) {
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
                local.body[property] = merged;
                return local;
            } else {
                return local.deleted ? local : remote;
            }
        };
    },
};
