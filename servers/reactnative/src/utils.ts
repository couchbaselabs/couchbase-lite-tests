// Utility functions for the React Native TDK test server.
//
// Copyright 2025-Present Couchbase, Inc.
//
// Use of this software is governed by the Business Source License included
// in the file licenses/BSL-Couchbase.txt.  As of the Change Date specified
// in that file, in accordance with the Business Source License, use of this
// software will be governed by the Apache License, Version 2.0, included in
// the file licenses/APL2.txt.

export type JSONValue =
  | string
  | number
  | boolean
  | null
  | JSONObject
  | JSONArray;
export type JSONObject = {[key: string]: JSONValue};
export type JSONArray = JSONValue[];

export class HTTPError extends Error {
  public readonly domain = 'HTTP';
  constructor(
    public readonly code: number,
    message?: string,
  ) {
    super(message);
    this.name = 'HTTP';
  }
}

export function check(cond: boolean, message: string): asserts cond {
  if (!cond) {
    throw new HTTPError(400, message);
  }
}

export function normalizeCollectionID(id: string): string {
  return id.startsWith('_default.') ? id.substring(9) : id;
}

export function collectionIDWithScope(id: string): string {
  return id.includes('.') ? id : `_default.${id}`;
}

export function isObject(
  val: JSONValue | undefined,
): val is JSONObject {
  return typeof val === 'object' && val !== null && !Array.isArray(val);
}

export function isDict(
  val: JSONValue | undefined,
): val is JSONObject {
  return typeof val === 'object' && val !== null && !Array.isArray(val);
}
