// KeyPath parser for reading/writing nested object/array properties.
// Ported directly from the JavaScript server's keyPath.ts.
//
// Copyright 2025-Present Couchbase, Inc.
//
// Use of this software is governed by the Business Source License included
// in the file licenses/BSL-Couchbase.txt.  As of the Change Date specified
// in that file, in accordance with the Business Source License, use of this
// software will be governed by the Apache License, Version 2.0, included in
// the file licenses/APL2.txt.

import type {JSONValue} from './utils';
import {HTTPError, isDict} from './utils';

type KeyPathComponents = Array<string | number>;

export class KeyPath {
  readonly components: KeyPathComponents = [];
  readonly str: string;

  constructor(readonly path: string) {
    function localCheck(cond: boolean): asserts cond {
      if (!cond) {
        throw new HTTPError(400, `Invalid KeyPath '${path}'`);
      }
    }

    let str = path.trim();
    if (str.startsWith('$')) {
      str = str.substring(1);
    } else if (!str.startsWith('[')) {
      str = '.' + str;
    }

    let i = 0;
    while (i < str.length) {
      const m = str.substring(i).match(/\.([^.[]*)|\[(-?\d+)\]/);
      localCheck(m !== null);
      if (m![0].startsWith('.')) {
        const key = m![1];
        localCheck(key.length > 0);
        this.components.push(key);
      } else {
        const n = Number(m![2]);
        localCheck(Number.isSafeInteger(n));
        this.components.push(n);
      }
      i += m![0].length;
    }

    this.str = str;
  }

  static componentsToString(pathComps: KeyPathComponents): string {
    if (pathComps.length === 0) {
      return '.';
    }
    return pathComps
      .flatMap(item =>
        typeof item === 'string' ? ['.', item] : `[${item}]`,
      )
      .join('');
  }

  read(root: JSONValue): JSONValue | undefined {
    let cur: JSONValue | undefined = root;
    for (const c of this.components) {
      if (typeof c === 'string') {
        cur = isDict(cur) ? (cur as any)[c] : undefined;
      } else {
        cur = Array.isArray(cur) ? cur[c] : undefined;
      }
      if (cur === undefined) {
        break;
      }
    }
    return cur;
  }

  write(root: JSONValue, value: JSONValue | undefined): boolean {
    const makeCollection = (i: number): JSONValue =>
      typeof this.components[i] === 'string' ? {} : [];

    let cur: any = root;
    const last = this.components.length - 1;
    for (let i = 0; i <= last; ++i) {
      const c = this.components[i];
      if (typeof c === 'string') {
        if (!isDict(cur)) {
          return false;
        }
        if (i === last) {
          if (value !== undefined) {
            cur[c] = value;
          } else {
            delete cur[c];
          }
        } else if (c in cur) {
          cur = cur[c];
        } else {
          cur = cur[c] = makeCollection(i + 1);
        }
      } else {
        if (!Array.isArray(cur)) {
          return false;
        }
        if (i < last && cur.length >= c) {
          cur = cur[c];
        } else {
          while (cur.length < c) {
            cur.push(null);
          }
          if (i === last) {
            if (value !== undefined) {
              cur[c] = value;
            } else {
              cur.splice(c, 1);
            }
          } else {
            cur = cur[c] = makeCollection(i + 1);
          }
        }
      }
    }
    return true;
  }

  static read(root: JSONValue, pathStr: string): JSONValue | undefined {
    return new KeyPath(pathStr).read(root);
  }

  static write(
    root: JSONValue,
    pathStr: string,
    value: JSONValue | undefined,
  ): boolean {
    return new KeyPath(pathStr).write(root, value);
  }

  toString(): string {
    return this.str;
  }
}

export class KeyPathCache {
  private paths = new Map<string, KeyPath>();
  private static sharedInstance?: KeyPathCache;

  path(str: string): KeyPath {
    let kp = this.paths.get(str);
    if (!kp) {
      kp = new KeyPath(str);
      this.paths.set(str, kp);
    }
    return kp;
  }

  static path(str: string): KeyPath {
    if (!this.sharedInstance) {
      this.sharedInstance = new KeyPathCache();
    }
    return this.sharedInstance.path(str);
  }
}
