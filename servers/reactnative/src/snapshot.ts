// Snapshot and verification logic for React Native TDK.
// Adapted from the JavaScript server's snapshot.ts.
//
// Copyright 2025-Present Couchbase, Inc.
//
// Use of this software is governed by the Business Source License included
// in the file licenses/BSL-Couchbase.txt.  As of the Change Date specified
// in that file, in accordance with the Business Source License, use of this
// software will be governed by the Apache License, Version 2.0, included in
// the file licenses/APL2.txt.

import {HTTPError, normalizeCollectionID, isObject} from './utils';
import {KeyPath, KeyPathCache} from './keyPath';
import type * as tdk from './tdkSchema';
import type {JSONValue, JSONObject} from './utils';
import {
  Database,
  Collection,
  MutableDocument,
} from 'cbl-reactnative';

export type BlobLoader = (blobURL: string) => Promise<JSONValue>;

type GetDocumentFn = (
  dbName: string,
  scopeName: string,
  collectionName: string,
  docId: string,
) => Promise<JSONObject | null>;

type GetCollectionFn = (
  dbName: string,
  scopeName: string,
  collectionName: string,
) => Promise<{scope: string; collection: string}>;

export class Snapshot {
  readonly dbName: string;
  private documents = new DocumentMap<JSONObject | null>();
  private getDocFn: GetDocumentFn;

  constructor(dbName: string, getDocFn: GetDocumentFn) {
    this.dbName = dbName;
    this.getDocFn = getDocFn;
  }

  async record(collectionFullName: string, id: string): Promise<void> {
    const {scope, collection} = parseCollectionName(collectionFullName);
    const doc = await this.getDocFn(this.dbName, scope, collection, id);
    this.documents.set(collectionFullName, id, doc);
  }

  async verify(
    changes: readonly tdk.DatabaseUpdateItem[],
    blobLoader: BlobLoader,
  ): Promise<tdk.VerifyDocumentsResponse> {
    const updates = new DocumentMap<tdk.DatabaseUpdateItem>();
    for (const u of changes) {
      if (this.documents.get(u.collection, u.documentID) === undefined) {
        throw new HTTPError(
          400,
          `Update for unknown document ${u.documentID} in collection ${u.collection}`,
        );
      }
      updates.set(u.collection, u.documentID, u);
    }

    for (const [collectionFullName, id, oldDoc] of this.documents) {
      const update = updates.get(collectionFullName, id);
      if (oldDoc || update) {
        let expected: JSONObject | null | undefined;

        if (oldDoc) {
          if (update) {
            expected = await this.applyUpdate(
              {...oldDoc},
              update,
              blobLoader,
            );
          } else {
            expected = oldDoc;
          }
        } else {
          const emptyDoc: JSONObject = {};
          expected = await this.applyUpdate(emptyDoc, update!, blobLoader);
        }

        const {scope, collection} = parseCollectionName(collectionFullName);
        const newDoc = await this.getDocFn(
          this.dbName,
          scope,
          collection,
          id,
        );

        const result = this.compareDocs(expected, newDoc, update?.type);
        if (result !== undefined) {
          result.result = false;
          result.description = `Document ${id} in collection ${collectionFullName} ${result.description}`;
          if (update?.type === 'UPDATE' && newDoc) {
            result.document = newDoc;
          }
          return result;
        }
      } else {
        const {scope, collection} = parseCollectionName(collectionFullName);
        const foundDoc = await this.getDocFn(
          this.dbName,
          scope,
          collection,
          id,
        );
        if (foundDoc) {
          return {
            result: false,
            description: `Document ${id} in collection ${collectionFullName} should not exist`,
          };
        }
      }
    }
    return {result: true};
  }

  private async applyUpdate(
    doc: JSONObject,
    update: tdk.DatabaseUpdateItem,
    blobLoader: BlobLoader,
  ): Promise<JSONObject | null> {
    if (update.type !== 'UPDATE') {
      return null;
    }

    const patch = (key: string, value: JSONValue | undefined) => {
      if (!KeyPathCache.path(key).write(doc, value)) {
        throw new HTTPError(400, `Type mismatch traversing path ${key}`);
      }
    };

    if (update.updatedProperties !== undefined) {
      for (const props of update.updatedProperties) {
        for (const key of Object.getOwnPropertyNames(props)) {
          patch(key, props[key]);
        }
      }
    }
    if (update.removedProperties !== undefined) {
      for (const key of update.removedProperties) {
        patch(key, undefined);
      }
    }
    if (update.updatedBlobs !== undefined) {
      for (const key of Object.getOwnPropertyNames(update.updatedBlobs)) {
        const blobMeta = await blobLoader(update.updatedBlobs[key]);
        patch(key, blobMeta);
      }
    }
    return doc;
  }

  private compareDocs(
    expected: JSONObject | null | undefined,
    actual: JSONObject | null,
    updateType: string | undefined,
  ): tdk.VerifyDocumentsResponse | undefined {
    let response: tdk.VerifyDocumentsResponse | undefined;
    const path: Array<string | number> = [];

    // The bridge saves blobs in { _type: 'blob', data: {...} } format but reads them
    // back as { '@type': 'blob', content_type, digest, length } via doc.toJSON().
    // Treat any blob object as equal to any other blob object — presence is sufficient.
    const isBlob = (val: JSONValue | undefined): boolean => {
      if (typeof val !== 'object' || val === null || Array.isArray(val)) {
        return false;
      }
      const o = val as JSONObject;
      return o['_type'] === 'blob' || o['@type'] === 'blob';
    };

    const compare = (
      exp?: JSONValue,
      act?: JSONValue,
    ): boolean => {
      const fail = (): false => {
        response = {
          result: false,
          description: `had unexpected properties at ${KeyPath.componentsToString(path)}`,
          actual: act ?? null,
          expected: exp ?? null,
        };
        return false;
      };

      if (typeof exp !== typeof act) {
        return fail();
      }
      if (typeof exp !== 'object' || exp === null) {
        return exp === act || fail();
      } else if (Array.isArray(exp)) {
        if (!Array.isArray(act)) {
          return fail();
        }
        const maxLen = Math.max(exp.length, (act as JSONValue[]).length);
        for (let i = 0; i < maxLen; ++i) {
          path.push(i);
          if (!compare(exp[i], (act as JSONValue[])[i])) {
            return false;
          }
          path.pop();
        }
        return true;
      } else {
        if (Array.isArray(act)) {
          return fail();
        }
        // Blob-aware comparison: bridge save format (_type) vs read format (@type).
        if (isBlob(exp) && isBlob(act)) {
          return true;
        }
        if (isBlob(exp) || isBlob(act)) {
          return fail();
        }
        const actObj = act as JSONObject;
        const expKeys = Object.keys(exp);
        const actKeys = Object.keys(actObj);
        for (const key of expKeys) {
          path.push(key);
          if (!compare((exp as JSONObject)[key], actObj[key])) {
            return false;
          }
          path.pop();
        }
        if (actKeys.length > expKeys.length) {
          for (const key of actKeys) {
            path.push(key);
            if (
              !compare((exp as JSONObject)[key], actObj[key])
            ) {
              return false;
            }
            path.pop();
          }
        }
        return true;
      }
    };

    if (expected) {
      if (actual) {
        compare(expected, actual);
      } else {
        response = {
          result: false,
          description: 'was not found',
        };
      }
    } else {
      if (actual) {
        response = {
          result: false,
          description: 'should not exist',
        };
        if (updateType === 'DELETE') {
          response.description = 'was not deleted';
        } else if (updateType === 'PURGE') {
          response.description = 'was not purged';
        }
      }
    }

    return response;
  }
}

function parseCollectionName(fullName: string): {
  scope: string;
  collection: string;
} {
  const normalized = normalizeCollectionID(fullName);
  if (fullName.includes('.')) {
    const parts = fullName.split('.');
    return {scope: parts[0], collection: parts[1]};
  }
  return {scope: '_default', collection: normalized};
}

class DocumentMap<T> {
  private map = new Map<string, Map<string, T>>();

  set(collection: string, id: string, value: T): void {
    let coll = this.map.get(collection);
    if (coll === undefined) {
      coll = new Map<string, T>();
      this.map.set(collection, coll);
    }
    coll.set(id, value);
  }

  get(collection: string, id: string): T | undefined {
    return this.map.get(collection)?.get(id);
  }

  *[Symbol.iterator](): Generator<[string, string, T]> {
    for (const [collection, docs] of this.map) {
      for (const [id, doc] of docs) {
        yield [collection, id, doc];
      }
    }
  }
}
