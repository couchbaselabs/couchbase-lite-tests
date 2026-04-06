// TDK implementation for the React Native test server.
// Implements all API endpoint handlers using cbl-reactnative SDK.
//
// Copyright 2025-Present Couchbase, Inc.
//
// Use of this software is governed by the Business Source License included
// in the file licenses/BSL-Couchbase.txt.  As of the Change Date specified
// in that file, in accordance with the Business Source License, use of this
// software will be governed by the Apache License, Version 2.0, included in
// the file licenses/APL2.txt.

import {Platform} from 'react-native';
import {
  CblReactNativeEngine,
  Database,
  DatabaseConfiguration,
  MutableDocument,
  MaintenanceType,
  Replicator,
  ReplicatorConfiguration,
  URLEndpoint,
  BasicAuthenticator,
  SessionAuthenticator,
  ReplicatorActivityLevel,
  Collection,
  CollectionConfig,
} from 'cbl-reactnative';

import {KeyPathCache} from './keyPath';
import {LogSlurpSender} from './logSlurpSender';
import {
  check,
  HTTPError,
  isObject,
  normalizeCollectionID,
  collectionIDWithScope,
} from './utils';
import {Snapshot} from './snapshot';
import type {TestRequest} from './testServer';
import type {JSONObject, JSONValue} from './utils';
import * as tdk from './tdkSchema';

interface ReplicatorInfo {
  replicatorId: string;
  database: string;
  documents?: tdk.DocumentReplication[];
  statusListenerToken?: string;
  docListenerToken?: string;
  finished: boolean;
  error?: Error;
  cbError?: {domain: string; code: number; message: string};
}

export const APIVersion = 1;

export class TDKImpl implements tdk.TDK {
  private engine: CblReactNativeEngine;
  private databases = new Map<string, string>();
  private replicators = new Map<string, ReplicatorInfo>();
  private snapshots = new Map<string, Snapshot>();
  private idCounter = 0;
  private snapshotCounter = 0;
  private sessionID?: string;
  private logSender?: LogSlurpSender;

  onLog?: (message: string) => void;

  constructor() {
    this.engine = new CblReactNativeEngine();
  }

  private log(message: string): void {
    console.log(`[TDK] ${message}`);
    this.onLog?.(message);
    this.logSender?.sendLogMessage(`[TDK] ${message}`);
  }

  async dispose(): Promise<void> {
    await this.closeDatabases();
    this.logSender?.close();
    this.logSender = undefined;
  }

  private async closeDatabases(): Promise<void> {
    for (const [id, info] of this.replicators) {
      if (!info.finished) {
        this.log(`Reset: Stopping replicator ${id}`);
        try {
          await this.engine.replicator_Stop({replicatorId: info.replicatorId});
        } catch (e) {
          this.log(`Error stopping replicator ${id}: ${e}`);
        }
      }
      this.log(`Reset: Cleaning up replicator ${id}`);
      try {
        await this.engine.replicator_Cleanup({
          replicatorId: info.replicatorId,
        });
      } catch (e) {
        this.log(`Error cleaning up replicator ${id}: ${e}`);
      }
    }
    this.replicators.clear();

    for (const [dbName, uniqueName] of this.databases) {
      this.log(`Reset: Deleting database ${dbName} (${uniqueName})`);
      try {
        await this.engine.database_Delete({name: uniqueName});
      } catch (e) {
        this.log(`Error deleting database ${dbName}: ${e}`);
        try {
          await this.engine.database_Close({name: uniqueName});
        } catch (e2) {
          this.log(`Error closing database ${dbName}: ${e2}`);
        }
      }
    }
    this.databases.clear();
    this.snapshots.clear();
  }

  // ======== NEW SESSION ========

  async [tdk.NewSessionCommand](rq: tdk.NewSessionRequest): Promise<void> {
    check(this.sessionID === undefined, "Can't start a second session");
    this.sessionID = rq.id;
    if (rq.logging) {
      this.log(
        `Connecting to LogSlurp at ${rq.logging.url} with id=${rq.id}, tag=${rq.logging.tag}`,
      );
      this.logSender = new LogSlurpSender(
        rq.logging.url,
        rq.id,
        rq.logging.tag,
      );
      try {
        await this.logSender.waitForConnected(5000);
      } catch (e) {
        this.log(`Warning: LogSlurp connection failed: ${e}`);
      }
    }
  }

  // ======== GET INFO ========

  async [tdk.GetInfoCommand](
    _rq: TestRequest,
  ): Promise<tdk.GetInfoResponse> {
    return {
      version: '1.0.0',
      apiVersion: APIVersion,
      cbl: 'cbl-reactnative',
      device: {
        systemName: Platform.OS,
        systemVersion: String(Platform.Version),
        model: 'React Native Device',
      },
    };
  }

  // ======== RESET ========

  async [tdk.ResetCommand](rq: tdk.ResetRequest): Promise<void> {
    this.log(`[DIAG] ResetCommand: start — test="${rq.test ?? '(none)'}", databases=${JSON.stringify(Object.keys(rq.databases ?? {}))}`);
    await this.closeDatabases();
    this.log(`[DIAG] ResetCommand: closeDatabases complete`);
    if (rq.databases) {
      const dbNames = Object.getOwnPropertyNames(rq.databases);
      this.log(`[DIAG] ResetCommand: ${dbNames.length} database(s) to set up: ${dbNames.join(', ')}`);
      for (const name of dbNames) {
        const what = rq.databases[name];
        const hasDataset = 'dataset' in what;
        this.log(`[DIAG] ResetCommand: setting up db="${name}" hasDataset=${hasDataset} spec=${JSON.stringify(what)}`);
        if (hasDataset) {
          this.log(`[DIAG] ResetCommand: calling loadDataset("${name}", "${(what as any).dataset}")`);
          await this.loadDataset(name, (what as any).dataset);
          this.log(`[DIAG] ResetCommand: loadDataset complete for db="${name}"`);
        } else {
          this.log(`[DIAG] ResetCommand: calling createDatabase("${name}", collections=${JSON.stringify((what as any).collections)})`);
          await this.createDatabase(name, (what as any).collections);
          this.log(`[DIAG] ResetCommand: createDatabase complete for db="${name}"`);
        }
      }
    } else {
      this.log(`[DIAG] ResetCommand: no databases in request`);
    }
    if (rq.test) {
      this.log(`>>>>>>>>>> ${rq.test}`);
    }
    this.log(`[DIAG] ResetCommand: done`);
  }

  // ======== GET ALL DOCUMENTS ========

  async [tdk.GetAllDocumentsCommand](
    rq: tdk.GetAllDocumentsRequest,
  ): Promise<tdk.GetAllDocumentsResponse> {
    this.log(`[DIAG] GetAllDocuments: start db="${rq.database}" collections=${JSON.stringify(rq.collections)}`);
    const uniqueName = this.getDatabase(rq.database);
    this.log(`[DIAG] GetAllDocuments: resolved uniqueName="${uniqueName}"`);
    const response: any = {};

    for (const inputColl of rq.collections) {
      this.log(`[DIAG] GetAllDocuments: processing collection "${inputColl}"`);
      const {scope, collection} = this.parseCollectionName(inputColl);
      this.log(`[DIAG] GetAllDocuments: "${inputColl}" → scope="${scope}" collection="${collection}"`);
      const docs: Array<{id: string; rev: string}> = [];
      response[inputColl] = docs;

      try {
        const queryStr = `SELECT META().id, META().revisionID FROM \`${scope}\`.\`${collection}\``;
        this.log(`getAllDocuments: executing query on db="${uniqueName}": ${queryStr}`);
        this.log(`[DIAG] GetAllDocuments: executing query: ${queryStr}`);
        const result = await this.engine.query_Execute({
          query: queryStr,
          parameters: {},
          name: uniqueName,
        });
        this.log(`[DIAG] GetAllDocuments: query_Execute result keys=${result ? Object.keys(result as any).join(',') : 'null'}`);

        const rawData = (result as any)?.data ?? (result as any)?._data;
        this.log(`[DIAG] GetAllDocuments: rawData type=${typeof rawData} truthy=${!!rawData} length=${typeof rawData === 'string' ? rawData.length : 'N/A'}`);
        if (rawData) {
          const rows = JSON.parse(rawData);
          this.log(`[DIAG] GetAllDocuments: parsed ${rows.length} rows for "${inputColl}"`);
          let skipped = 0;
          for (const row of rows) {
            if (row.id && row.revisionID) {
              docs.push({id: row.id, rev: row.revisionID});
            } else {
              skipped++;
              this.log(`[DIAG] GetAllDocuments: skipped row (missing id or revisionID) rawRow=${JSON.stringify(row)}`);
            }
          }
          this.log(`getAllDocuments: ${inputColl} → ${docs.length} docs (${rows.length} rows total, ${skipped} skipped for missing id/rev)`);
          this.log(`[DIAG] GetAllDocuments: [${inputColl}] RESULT docs=${docs.length} skipped=${skipped} firstDocId=${docs[0]?.id ?? 'none'} lastDocId=${docs[docs.length - 1]?.id ?? 'none'}`);
        } else {
          this.log(`getAllDocuments: ${inputColl} → rawData is ${rawData === undefined ? 'undefined' : 'null/empty'} (result keys: ${result ? Object.keys(result as any).join(',') : 'null'})`);
          this.log(`[DIAG] GetAllDocuments: NO rawData for "${inputColl}" — result=${JSON.stringify(result)}`);
        }
      } catch (e: any) {
        this.log(`Error in getAllDocuments for ${inputColl}: ${e}`);
        this.log(`[DIAG] GetAllDocuments: EXCEPTION for "${inputColl}": ${JSON.stringify(e)} message=${e?.message}`);
      }
    }
    this.log(`[DIAG] GetAllDocuments: done — summary: ${rq.collections.map(c => `${c}=${response[c]?.length ?? 'err'}`).join(', ')}`);
    return response;
  }

  // ======== GET DOCUMENT ========

  async [tdk.GetDocumentCommand](
    rq: tdk.GetDocumentRequest,
  ): Promise<tdk.GetDocumentResponse> {
    const uniqueName = this.getDatabase(rq.database);
    const {scope, collection} = this.parseCollectionName(
      rq.document.collection,
    );

    const result = await this.engine.collection_GetDocument({
      docId: rq.document.id,
      name: uniqueName,
      scopeName: scope,
      collectionName: collection,
    });

    // Bridge resolves with { _id, _sequence, _data } when found, {} when not found.
    const r = result as any;
    if (!r || !r._id) {
      throw new HTTPError(404, `No document "${rq.document.id}"`);
    }

    let body: JSONObject = {};
    const raw = r._data;
    if (typeof raw === 'string') {
      try {
        body = JSON.parse(raw);
      } catch (_e) {
        body = {};
      }
    } else if (raw && typeof raw === 'object') {
      body = raw as JSONObject;
    }

    const id = r._id || rq.document.id;
    const revId = r._revId || '';

    return {_id: id, _revs: revId, ...body};
  }

  // ======== UPDATE DATABASE ========

  async [tdk.UpdateDatabaseCommand](
    rq: tdk.UpdateDatabaseRequest,
  ): Promise<void> {
    const uniqueName = this.getDatabase(rq.database);

    for (const update of rq.updates) {
      const {scope, collection} = this.parseCollectionName(
        update.collection,
      );

      switch (update.type) {
        case 'UPDATE': {
          let existingDoc: JSONObject = {};
          let existingId = update.documentID;
          try {
            const docResult = await this.engine.collection_GetDocument({
              docId: update.documentID,
              name: uniqueName,
              scopeName: scope,
              collectionName: collection,
            });
            // Bridge returns { _id, _sequence, _data } when found, {} when not found.
            const dr = docResult as any;
            if (dr && dr._id) {
              const d = dr._data;
              if (typeof d === 'string') {
                existingDoc = JSON.parse(d);
              } else if (d && typeof d === 'object') {
                existingDoc = {...d};
              }
              existingId = dr._id || update.documentID;
            }
          } catch (_e) {
            // Document doesn't exist yet
          }

          if (update.updatedProperties) {
            for (const props of update.updatedProperties) {
              for (const pathStr of Object.getOwnPropertyNames(props)) {
                if (
                  !KeyPathCache.path(pathStr).write(
                    existingDoc,
                    props[pathStr],
                  )
                ) {
                  throw new HTTPError(
                    400,
                    `Invalid path ${pathStr} in doc ${update.documentID}`,
                  );
                }
              }
            }
          }
          if (update.removedProperties) {
            for (const pathStr of update.removedProperties) {
              if (
                !KeyPathCache.path(pathStr).write(
                  existingDoc,
                  undefined,
                )
              ) {
                throw new HTTPError(
                  400,
                  `Invalid path ${pathStr} in doc ${update.documentID}`,
                );
              }
            }
          }
          // Collect explicit blobs from updatedBlobs — these are passed directly to the
          // bridge's blobs parameter so their raw bytes never bloat the document JSON.
          // The native bridge calls setBlob(blob, forKey: path) for each entry.
          const explicitBlobs: Record<string, any> = {};
          if (update.updatedBlobs) {
            for (const pathStr of Object.getOwnPropertyNames(
              update.updatedBlobs,
            )) {
              const blobMeta = await this.downloadBlobMetadata(
                update.updatedBlobs[pathStr],
              );
              explicitBlobs[pathStr] = blobMeta;
            }
          }

          // Remove internal fields before saving
          delete (existingDoc as any)._id;
          delete (existingDoc as any)._revId;
          delete (existingDoc as any)._revisionID;
          delete (existingDoc as any)._sequence;

          // Extract any inline blobs already present in the document body
          // (e.g. from updatedProperties), then merge with explicitBlobs so the
          // bridge receives all blobs via the dedicated blobs channel.
          const extractedBlobs = this.extractBlobs(existingDoc);
          const blobs = {...extractedBlobs, ...explicitBlobs};

          await this.engine.collection_Save({
            id: existingId,
            document: JSON.stringify(existingDoc),
            blobs: JSON.stringify(blobs),
            name: uniqueName,
            scopeName: scope,
            collectionName: collection,
            concurrencyControl: null,
          });
          break;
        }
        case 'DELETE': {
          await this.engine.collection_DeleteDocument({
            docId: update.documentID,
            name: uniqueName,
            scopeName: scope,
            collectionName: collection,
            concurrencyControl: 1, // lastWriteWins
          });
          break;
        }
        case 'PURGE': {
          await this.engine.collection_PurgeDocument({
            docId: update.documentID,
            name: uniqueName,
            scopeName: scope,
            collectionName: collection,
          });
          break;
        }
      }
    }
  }

  // ======== START REPLICATOR ========

  async [tdk.StartReplicatorCommand](
    rq: tdk.StartReplicatorRequest,
  ): Promise<tdk.StartReplicatorResponse> {
    this.log(`[DIAG] StartReplicator: start — type=${rq.config.replicatorType} continuous=${rq.config.continuous} endpoint=${rq.config.endpoint} db=${rq.config.database} enableDocListener=${rq.config.enableDocumentListener}`);
    this.log(`[DIAG] StartReplicator: collections input=${JSON.stringify(rq.config.collections)}`);

    const uniqueName = this.getDatabase(rq.config.database);
    this.log(`[DIAG] StartReplicator: resolved db="${rq.config.database}" → uniqueName="${uniqueName}"`);

    // Build collectionConfig JSON string (NEW API format)
    const collectionConfigArray: any[] = [];
    const totalColls = rq.config.collections.reduce((n, c) => n + c.names.length, 0);
    this.log(`Building collectionConfig for ${totalColls} collection(s)`);
    this.log(`[DIAG] StartReplicator: building collectionConfig — ${rq.config.collections.length} group(s), ${totalColls} total collection(s)`);

    for (const colls of rq.config.collections) {
      this.log(`[DIAG] StartReplicator: group channels=${JSON.stringify(colls.channels)} documentIDs=${JSON.stringify(colls.documentIDs)} names=${JSON.stringify(colls.names)}`);
      for (const collName of colls.names) {
        this.log(`[DIAG] StartReplicator: parseCollectionName("${collName}")`);
        const {scope, collection} = this.parseCollectionName(collName);
        this.log(`  collection: "${collName}" → scope="${scope}" name="${collection}" db="${uniqueName}"`);
        this.log(`[DIAG] StartReplicator: "${collName}" → scope="${scope}" collection="${collection}"`);

        // Build filter function strings (serialized JS evaluated by native JavaScriptCore/Rhino)
        let pushFilterStr: string | null = null;
        let pullFilterStr: string | null = null;

        if (colls.pushFilter) {
          pushFilterStr = this.createFilterFunction(colls.pushFilter, collName);
          this.log(`[DIAG] StartReplicator: pushFilter "${colls.pushFilter.name}" → function created for "${collName}"`);
        }
        if (colls.pullFilter) {
          pullFilterStr = this.createFilterFunction(colls.pullFilter, collName);
          this.log(`[DIAG] StartReplicator: pullFilter "${colls.pullFilter.name}" → function created for "${collName}"`);
        }
        if (colls.conflictResolver) {
          this.validateConflictResolverName(colls.conflictResolver.name);
          throw new HTTPError(
            501,
            `Conflict resolver "${colls.conflictResolver.name}" is not supported by the cbl-reactnative native SDK`,
          );
        }

        const entry = {
          collection: {
            name: collection,
            scopeName: scope,
            databaseName: uniqueName,
          },
          config: {
            channels: colls.channels ?? [],
            documentIds: colls.documentIDs ?? [],
            pushFilter: pushFilterStr,
            pullFilter: pullFilterStr,
          },
        };
        this.log(`[DIAG] StartReplicator: collectionEntry for "${collName}": channels=${JSON.stringify(colls.channels)} documentIds=${JSON.stringify(colls.documentIDs)} pushFilter=${pushFilterStr ? colls.pushFilter!.name : 'null'} pullFilter=${pullFilterStr ? colls.pullFilter!.name : 'null'}`);
        collectionConfigArray.push(entry);
      }
    }
    this.log(`[DIAG] StartReplicator: full collectionConfigArray=${JSON.stringify(collectionConfigArray)}`);

    // Convert PEM certificate to base64 DER if present
    let pinnedCertBase64 = '';
    this.log(`[DIAG] StartReplicator: pinnedServerCert present=${!!rq.config.pinnedServerCert}`);
    if (rq.config.pinnedServerCert) {
      const pem = rq.config.pinnedServerCert
        .replace(/-----BEGIN CERTIFICATE-----/g, '')
        .replace(/-----END CERTIFICATE-----/g, '')
        .replace(/\s/g, '');
      pinnedCertBase64 = pem;
      this.log(`[DIAG] StartReplicator: pinnedCertBase64 length=${pinnedCertBase64.length}`);
    }

    const config: any = {
      target: {url: rq.config.endpoint},
      replicatorType:
        rq.config.replicatorType === 'push'
          ? 'PUSH'
          : rq.config.replicatorType === 'pull'
            ? 'PULL'
            : 'PUSH_AND_PULL',
      continuous: rq.config.continuous ?? false,
      acceptParentDomainCookies: false,
      acceptSelfSignedCerts: false,
      allowReplicationInBackground: false,
      autoPurgeEnabled: rq.config.enableAutoPurge ?? true,
      heartbeat: 300,
      maxAttempts: 10,
      maxAttemptWaitTime: 300,
      pinnedServerCertificate: pinnedCertBase64,
      headers: rq.config.headers ?? {},
      collectionConfig: JSON.stringify(collectionConfigArray),
    };

    this.log(`[DIAG] StartReplicator: config.replicatorType="${config.replicatorType}" config.continuous=${config.continuous} config.autoPurgeEnabled=${config.autoPurgeEnabled}`);

    if (rq.config.authenticator) {
      this.log(`[DIAG] StartReplicator: authenticator type="${rq.config.authenticator.type}"`);
      if (rq.config.authenticator.type === 'BASIC') {
        const basicAuth =
          rq.config.authenticator as tdk.ReplicatorBasicAuthenticator;
        config.authenticator = {
          type: 'basic',
          data: {
            username: basicAuth.username,
            password: basicAuth.password,
          },
        };
        this.log(`[DIAG] StartReplicator: BASIC auth username="${basicAuth.username}"`);
      } else if (rq.config.authenticator.type === 'SESSION') {
        const sessAuth =
          rq.config.authenticator as tdk.ReplicatorSessionAuthenticator;
        config.authenticator = {
          type: 'session',
          data: {
            sessionID: sessAuth.sessionID,
            cookieName: sessAuth.cookieName,
          },
        };
        this.log(`[DIAG] StartReplicator: SESSION auth cookieName="${sessAuth.cookieName}"`);
      }
    } else {
      this.log(`[DIAG] StartReplicator: no authenticator`);
    }

    this.log(`Creating replicator: type=${config.replicatorType}, endpoint=${config.target?.url}, continuous=${config.continuous}`);
    this.log(`  collectionConfig (JSON): ${config.collectionConfig}`);
    this.log(`[DIAG] StartReplicator: calling replicator_Create — full config (no cert): type=${config.replicatorType} endpoint=${config.target?.url} continuous=${config.continuous} collectionConfig=${config.collectionConfig}`);

    const replResult = await this.engine.replicator_Create({
      config,
    });
    this.log(`[DIAG] StartReplicator: replicator_Create result=${JSON.stringify(replResult)}`);
    const replicatorId = replResult.replicatorId;
    this.log(`Replicator created successfully: replicatorId=${replicatorId}`);
    this.log(`[DIAG] StartReplicator: replicatorId="${replicatorId}"`);

    const id = `repl-${++this.idCounter}`;
    this.log(`[DIAG] StartReplicator: internal id="${id}"`);
    const info: ReplicatorInfo = {
      replicatorId,
      database: rq.config.database,
      documents: rq.config.enableDocumentListener ? [] : undefined,
      finished: false,
    };

    // ALWAYS add a diagnostic document change listener to see what gets pushed/pulled and any errors
    try {
      const diagDocToken = `diag-doc-listener-${id}`;
      this.log(`[DIAG] StartReplicator: adding DIAGNOSTIC doc listener token="${diagDocToken}"`);
      await this.engine.replicator_AddDocumentChangeListener(
        {
          changeListenerToken: diagDocToken,
          replicatorId: replicatorId,
        },
          (data: any, error?: any) => {
          if (error) {
            this.log(`[DIAG] DocListener ${id}: callback error=${JSON.stringify(error)}`);
            return;
          }
          const isPush = data?.isPush ?? data?.push ?? false;
          const docs = data?.documents ?? data?.docs ?? [];
          this.log(`[DIAG] DocListener ${id}: event isPush=${isPush} docCount=${Array.isArray(docs) ? docs.length : 'N/A'} rawKeys=${JSON.stringify(Object.keys(data ?? {}))}`);
          if (Array.isArray(docs)) {
            for (const doc of docs) {
              const docID = doc.documentID ?? doc.id ?? doc.docID ?? '(unknown)';
              const scope = doc.scopeName ?? doc.scope ?? '_default';
              const coll = doc.collectionName ?? doc.collection ?? '_default';
              const docError = doc.error ?? doc.replicationError;
              const docFlags: string[] = Array.isArray(doc.flags) ? doc.flags : [];
              this.log(`[DIAG] DocListener ${id}: doc="${docID}" scope="${scope}" collection="${coll}" isPush=${isPush} flags=${JSON.stringify(docFlags)} error=${docError ? JSON.stringify(docError) : 'none'}`);
            }
          } else {
            this.log(`[DIAG] DocListener ${id}: raw data=${JSON.stringify(data)}`);
          }
        },
      );
      this.log(`[DIAG] StartReplicator: diagnostic doc listener added OK`);
    } catch (e) {
      this.log(`[DIAG] StartReplicator: FAILED to add diagnostic doc listener: ${e}`);
    }

    // Add status change listener
    if (rq.config.enableDocumentListener) {
      this.log(`[DIAG] StartReplicator: enableDocumentListener=true — adding official doc listener`);
      try {
        const docToken = `doc-listener-${id}`;
        await this.engine.replicator_AddDocumentChangeListener(
          {
            changeListenerToken: docToken,
            replicatorId: replicatorId,
          },
          (data: any, error?: any) => {
            if (info.documents === undefined) {
              info.documents = [];
            }
            const isPush = data?.isPush ?? false;
            const docs = data?.documents;
            if (docs && Array.isArray(docs)) {
              for (const doc of docs) {
                // The native bridge sends flags as a string array (e.g. ["DELETED", "ACCESS_REMOVED"]),
                // not as boolean properties doc.deleted / doc.accessRemoved.
                const docFlags: string[] = Array.isArray(doc.flags) ? doc.flags : [];
                const flags: Array<'deleted' | 'accessRemoved'> = [];
                if (docFlags.some((f: string) => f.toUpperCase() === 'DELETED')) {
                  flags.push('deleted');
                }
                if (
                  docFlags.some(
                    (f: string) =>
                      f.toUpperCase() === 'ACCESS_REMOVED' ||
                      f.toUpperCase() === 'ACCESSREMOVED',
                  )
                ) {
                  flags.push('accessRemoved');
                }
                info.documents.push({
                  collection: doc.scopeName
                    ? `${doc.scopeName}.${doc.collectionName}`
                    : collectionIDWithScope(doc.collectionName || ''),
                  documentID: doc.documentID || doc.id || '',
                  isPush: isPush,
                  flags,
                  error: doc.error
                    ? {
                        domain: 'CBL',
                        code: doc.error.code ?? -1,
                        message: doc.error.message ?? '',
                      }
                    : undefined,
                });
              }
            }
          },
        );
        info.docListenerToken = docToken;
        this.log(`[DIAG] StartReplicator: official doc listener added OK`);
      } catch (e) {
        this.log(`Warning: Could not add document listener: ${e}`);
        this.log(`[DIAG] StartReplicator: FAILED to add official doc listener: ${e}`);
      }
    }

    // Add status change listener to track completion
    this.log(`[DIAG] StartReplicator: adding status change listener`);
    try {
      const statusToken = `status-listener-${id}`;
      await this.engine.replicator_AddChangeListener(
        {
          changeListenerToken: statusToken,
          replicatorId: replicatorId,
        },
        (data: any, error?: any) => {
          if (data) {
            const activity =
              data.activityLevel ?? data.activity;
            const progress = data.progress;
            const completed = progress?.completed ?? progress?.completedSequences;
            const total = progress?.total ?? progress?.totalSequences;
            this.log(
              `Replicator ${id} status: activity=${activity}, completed=${completed}, total=${total}`,
            );
            this.log(`[DIAG] StatusListener ${id}: raw data=${JSON.stringify(data)}`);
            const cbError = data.error ?? data.replicatorError;
            if (cbError) {
              this.log(
                `Replicator ${id} callback error: domain=${cbError.domain}, code=${cbError.code}, message=${cbError.message ?? String(cbError)}`,
              );
              this.log(`[DIAG] StatusListener ${id}: ERROR=${JSON.stringify(cbError)}`);
            }
            if (
              activity === 0 ||
              activity === 'STOPPED' ||
              activity === 'stopped'
            ) {
              this.log(`Replicator ${id} STOPPED — final progress: completed=${completed}, total=${total}`);
              this.log(`[DIAG] StatusListener ${id}: STOPPED — full final data=${JSON.stringify(data)}`);
              info.finished = true;
              if (cbError && (cbError.code != null || cbError.message)) {
                const errDomain = typeof cbError.domain === 'string' ? cbError.domain : 'CBL';
                const errCode = cbError.code != null && !isNaN(Number(cbError.code)) ? Number(cbError.code) : -1;
                const errMsg = String(cbError.message ?? cbError);
                info.cbError = {domain: errDomain, code: errCode, message: errMsg};
                this.log(`[DIAG] StatusListener ${id}: captured cbError — domain="${errDomain}" code=${errCode} msg="${errMsg}"`);
              }
            }
          }
          if (error) {
            this.log(`Replicator ${id} listener error: ${error.message || String(error)}`);
            this.log(`[DIAG] StatusListener ${id}: listener-level error=${JSON.stringify(error)}`);
            const wrappedErr: any = new Error(error.message || String(error));
            if (error.domain != null) { wrappedErr.domain = error.domain; }
            if (error.code != null) { wrappedErr.code = Number(error.code); }
            info.error = wrappedErr;
          }
        },
      );
      info.statusListenerToken = statusToken;
      this.log(`[DIAG] StartReplicator: status listener added OK`);
    } catch (e) {
      this.log(`Warning: Could not add status listener: ${e}`);
      this.log(`[DIAG] StartReplicator: FAILED to add status listener: ${e}`);
    }

    this.replicators.set(id, info);
    this.log(`[DIAG] StartReplicator: replicator info stored in map under id="${id}"`);

    if (rq.reset) {
      this.log(`Resetting checkpoint for replicator ${id} (${replicatorId})`);
      this.log(`[DIAG] StartReplicator: rq.reset=true — calling replicator_ResetCheckpoint`);
      try {
        await this.engine.replicator_ResetCheckpoint({
          replicatorId: replicatorId,
        });
        this.log(`Checkpoint reset OK — starting replicator ${id}`);
        this.log(`[DIAG] StartReplicator: checkpoint reset OK — calling replicator_Start`);
        await this.engine.replicator_Start({replicatorId: replicatorId});
        this.log(`[DIAG] StartReplicator: replicator_Start (after reset) returned`);
      } catch (e) {
        this.log(`Warning: Reset checkpoint failed: ${e} — starting without reset`);
        this.log(`[DIAG] StartReplicator: reset checkpoint FAILED: ${e} — calling replicator_Start anyway`);
        await this.engine.replicator_Start({replicatorId: replicatorId});
        this.log(`[DIAG] StartReplicator: replicator_Start (fallback) returned`);
      }
    } else {
      this.log(`Starting replicator ${id} (${replicatorId})`);
      this.log(`[DIAG] StartReplicator: rq.reset=false — calling replicator_Start`);
      await this.engine.replicator_Start({replicatorId: replicatorId});
      this.log(`[DIAG] StartReplicator: replicator_Start returned`);
    }
    this.log(`Replicator ${id} started — waiting for status callbacks`);
    this.log(`[DIAG] StartReplicator: done — returning id="${id}"`);

    return {id};
  }

  // ======== STOP REPLICATOR ========

  async [tdk.StopReplicatorCommand](
    rq: tdk.StopReplicatorRequest,
  ): Promise<void> {
    const info = this.replicators.get(rq.id);
    if (!info) {
      throw new HTTPError(404, `No replicator with ID "${rq.id}"`);
    }
    await this.engine.replicator_Stop({replicatorId: info.replicatorId});
  }

  // ======== REPLICATOR STATUS ========

  async [tdk.GetReplicatorStatusCommand](
    rq: tdk.GetReplicatorStatusRequest,
  ): Promise<tdk.GetReplicatorStatusResponse> {
    this.log(`[DIAG] GetReplicatorStatus: called for id="${rq.id}"`);
    const info = this.replicators.get(rq.id);
    if (!info) {
      this.log(`[DIAG] GetReplicatorStatus: NO INFO found for id="${rq.id}"`);
      throw new HTTPError(404, `No replicator with ID "${rq.id}"`);
    }
    this.log(`[DIAG] GetReplicatorStatus: info found — replicatorId="${info.replicatorId}" finished=${info.finished} hasDocuments=${info.documents !== undefined}`);

    this.log(`[DIAG] GetReplicatorStatus: calling replicator_GetStatus replicatorId="${info.replicatorId}"`);
    const status = await this.engine.replicator_GetStatus({
      replicatorId: info.replicatorId,
    });
    this.log(`[DIAG] GetReplicatorStatus: raw status=${JSON.stringify(status)}`);

    let activity = 'CONNECTING';
    let statusError: tdk.ErrorInfo | undefined;
    if (status) {
      const level =
        (status as any).activityLevel ?? (status as any).activity;
      this.log(`GetStatus ${rq.id}: raw level=${JSON.stringify(level)}, status keys=${Object.keys(status as any).join(',')}`);
      this.log(`[DIAG] GetReplicatorStatus: raw level=${JSON.stringify(level)} allKeys=${Object.keys(status as any).join(',')}`);
      if (level === 0 || level === 'STOPPED' || level === 'stopped') {
        activity = 'STOPPED';
      } else if (
        level === 1 ||
        level === 'OFFLINE' ||
        level === 'offline'
      ) {
        activity = 'OFFLINE';
      } else if (
        level === 2 ||
        level === 'CONNECTING' ||
        level === 'connecting'
      ) {
        activity = 'CONNECTING';
      } else if (level === 3 || level === 'IDLE' || level === 'idle') {
        activity = 'IDLE';
      } else if (level === 4 || level === 'BUSY' || level === 'busy') {
        activity = 'BUSY';
      } else {
        this.log(`GetStatus ${rq.id}: UNKNOWN level=${JSON.stringify(level)} — defaulting to CONNECTING`);
        this.log(`[DIAG] GetReplicatorStatus: UNKNOWN level=${JSON.stringify(level)}`);
      }

      const rawProgress = (status as any).progress;
      const rawCompleted = rawProgress?.completed ?? rawProgress?.completedSequences;
      const rawTotal = rawProgress?.total ?? rawProgress?.totalSequences;
      this.log(`GetStatus ${rq.id}: mapped activity=${activity}, progress=${rawCompleted}/${rawTotal}`);
      this.log(`[DIAG] GetReplicatorStatus: mapped activity="${activity}" progress=${rawCompleted}/${rawTotal} rawProgress=${JSON.stringify(rawProgress)}`);

      const nativeError = (status as any).error;
      if (nativeError && nativeError.code != null && !isNaN(Number(nativeError.code))) {
        const msg = nativeError.message ?? String(nativeError);
        let domain = 'CBL';
        if (typeof nativeError.domain === 'string') {
          const d = nativeError.domain.toUpperCase();
          if (d.includes('POSIX')) domain = 'POSIX';
          else if (d.includes('SQLITE')) domain = 'SQLITE';
          else if (d.includes('FLEECE')) domain = 'FLEECE';
          else domain = 'CBL';
        }
        statusError = {
          domain,
          code: Number(nativeError.code),
          message: msg,
        };
        this.log(`GetStatus ${rq.id}: native error — domain=${domain}, code=${statusError.code}, message=${msg}`);
        this.log(`[DIAG] GetReplicatorStatus: NATIVE ERROR domain="${domain}" code=${statusError.code} message="${msg}" raw=${JSON.stringify(nativeError)}`);
      } else {
        this.log(`[DIAG] GetReplicatorStatus: no native error in status`);
      }
    } else {
      this.log(`GetStatus ${rq.id}: native returned null/undefined status`);
      this.log(`[DIAG] GetReplicatorStatus: status is null/undefined!`);
    }

    const documents = info.documents;
    info.documents = info.documents !== undefined ? [] : undefined;
    this.log(`[DIAG] GetReplicatorStatus: flushing ${documents?.length ?? 0} buffered doc events`);

    const errorResult = statusError
      || info.cbError
      || (info.error
        ? {
            domain: (info.error as any).domain ?? 'CBL',
            code: (info.error as any).code != null && !isNaN(Number((info.error as any).code)) ? Number((info.error as any).code) : -1,
            message: info.error.message,
          }
        : null);

    if (errorResult) {
      this.log(`GetStatus ${rq.id}: returning error to Python — ${errorResult.domain}/${errorResult.code}: ${errorResult.message}`);
      this.log(`[DIAG] GetReplicatorStatus: returning ERROR to Python — ${JSON.stringify(errorResult)}`);
    }
    this.log(`GetStatus ${rq.id}: returning activity=${activity} to Python`);
    this.log(`[DIAG] GetReplicatorStatus: returning activity="${activity}" finished=${info.finished}`);

    return {
      activity,
      progress: {completed: activity === 'STOPPED'},
      documents,
      error: errorResult,
    };
  }

  // ======== RUN QUERY ========

  async [tdk.RunQueryCommand](
    rq: tdk.RunQueryRequest,
  ): Promise<tdk.RunQueryResponse> {
    const uniqueName = this.getDatabase(rq.database);

    const result = await this.engine.query_Execute({
      query: rq.query,
      parameters: {},
      name: uniqueName,
    });

    let rows: any[] = [];
    if (result) {
      const rawData = (result as any).data ?? (result as any)._data;
      if (typeof rawData === 'string') {
        try {
          rows = JSON.parse(rawData);
        } catch (_e) {
          rows = [];
        }
      } else if (Array.isArray(result)) {
        rows = result;
      }
    }

    return {results: rows};
  }

  // ======== PERFORM MAINTENANCE ========

  async [tdk.PerformMaintenanceCommand](
    rq: tdk.PerformMaintenanceRequest,
  ): Promise<void> {
    const uniqueName = this.getDatabase(rq.database);

    let maintenanceType: number;
    switch (rq.maintenanceType) {
      case 'compact':
        maintenanceType = 0;
        break;
      case 'integrityCheck':
        maintenanceType = 2;
        break;
      case 'optimize':
        maintenanceType = 3;
        break;
      case 'fullOptimize':
        maintenanceType = 4;
        break;
      default:
        throw new HTTPError(501, 'Unimplemented maintenance type');
    }

    await this.engine.database_PerformMaintenance({
      maintenanceType: maintenanceType as any,
      name: uniqueName,
    });
  }

  // ======== SNAPSHOT DOCUMENTS ========

  async [tdk.SnapshotDocumentsCommand](
    rq: tdk.SnapshotDocumentsRequest,
  ): Promise<tdk.SnapshotDocumentsResponse> {
    const uniqueName = this.getDatabase(rq.database);
    const snap = new Snapshot(
      uniqueName,
      this.getDocumentAsJSON.bind(this),
    );
    for (const d of rq.documents) {
      await snap.record(d.collection, d.id);
    }
    const snapID = `snap-${++this.snapshotCounter}`;
    this.snapshots.set(snapID, snap);
    return {id: snapID};
  }

  // ======== VERIFY DOCUMENTS ========

  async [tdk.VerifyDocumentsCommand](
    rq: tdk.VerifyDocumentsRequest,
  ): Promise<tdk.VerifyDocumentsResponse> {
    const uniqueName = this.getDatabase(rq.database);
    const snap = this.snapshots.get(rq.snapshot);
    if (snap === undefined) {
      throw new HTTPError(404, `No such snapshot ${rq.snapshot}`);
    }
    if (snap.dbName !== uniqueName) {
      throw new HTTPError(
        400,
        `Snapshot is of a different database, ${rq.database}`,
      );
    }
    // Use a lightweight blob loader for verification: just signal "a blob exists here"
    // without downloading actual bytes. compareDocs treats any blob object as equal to
    // any other blob object, so the exact content doesn't matter for snapshot comparison.
    const verifyBlobLoader = async (_url: string) => ({_type: 'blob'} as const);
    return await snap.verify(rq.changes, verifyBlobLoader);
  }

  // ======== LOG ========

  async [tdk.LogCommand](rq: tdk.LogRequest): Promise<void> {
    this.log(`LOG: ${rq.message}`);
  }

  // ======== UNSUPPORTED: LISTENER ========

  async '/startListener'(_rq: TestRequest): Promise<never> {
    throw new HTTPError(
      501,
      'URLEndpointListener not supported in cbl-reactnative',
    );
  }

  async '/stopListener'(_rq: TestRequest): Promise<never> {
    throw new HTTPError(
      501,
      'URLEndpointListener not supported in cbl-reactnative',
    );
  }

  // ======== UNSUPPORTED: MULTIPEER ========

  async '/startMultipeerReplicator'(_rq: TestRequest): Promise<never> {
    throw new HTTPError(
      501,
      'Multipeer replication not supported in cbl-reactnative',
    );
  }

  async '/stopMultipeerReplicator'(_rq: TestRequest): Promise<never> {
    throw new HTTPError(
      501,
      'Multipeer replication not supported in cbl-reactnative',
    );
  }

  async '/getMultipeerReplicatorStatus'(
    _rq: TestRequest,
  ): Promise<never> {
    throw new HTTPError(
      501,
      'Multipeer replication not supported in cbl-reactnative',
    );
  }

  // ======== Internal helpers ========

  private static readonly KNOWN_FILTERS = new Set([
    'documentIDs',
    'deletedDocumentsOnly',
  ]);

  private static readonly KNOWN_CONFLICT_RESOLVERS = new Set([
    'local-wins',
    'remote-wins',
    'delete',
    'merge',
    'merge-dict',
  ]);

  private validateFilterName(name: string): void {
    if (!TDKImpl.KNOWN_FILTERS.has(name)) {
      throw new HTTPError(400, `Unknown replicator filter "${name}"`);
    }
  }

  private validateConflictResolverName(name: string): void {
    if (!TDKImpl.KNOWN_CONFLICT_RESOLVERS.has(name)) {
      throw new HTTPError(400, `Unknown conflict resolver "${name}"`);
    }
  }

  private getDatabase(name: string): string {
    const uniqueName = this.databases.get(name);
    if (!uniqueName) {
      throw new HTTPError(400, `No open database "${name}"`);
    }
    return uniqueName;
  }

  private async createDatabase(
    name: string,
    collections: readonly string[] | undefined,
  ): Promise<void> {
    this.log(`[DIAG] createDatabase: start name="${name}" collections=${JSON.stringify(collections)}`);
    check(
      !this.databases.has(name),
      `There is already an open database named ${name}`,
    );

    this.log(
      `Reset: Creating database ${name} with ${collections?.length ?? 0} collection(s)`,
    );

    this.log(`[DIAG] createDatabase: calling database_Open name="${name}"`);
    const result = await this.engine.database_Open({
      name: name,
      config: new DatabaseConfiguration(),
    });
    this.log(`[DIAG] createDatabase: database_Open result=${JSON.stringify(result)}`);
    const uniqueName = (result as any).databaseUniqueName ?? name;
    this.log(`Database ${name} opened with unique name: ${uniqueName}`);
    this.databases.set(name, uniqueName);

    if (collections) {
      this.log(`[DIAG] createDatabase: creating ${collections.length} collection(s)`);
      for (const collName of collections) {
        const {scope, collection} = this.parseCollectionName(collName);
        this.log(`[DIAG] createDatabase: parseCollectionName("${collName}") → scope="${scope}" collection="${collection}"`);
        try {
          this.log(`[DIAG] createDatabase: calling collection_CreateCollection scope="${scope}" collection="${collection}" db="${uniqueName}"`);
          await this.engine.collection_CreateCollection({
            collectionName: collection,
            name: uniqueName,
            scopeName: scope,
          });
          this.log(`[DIAG] createDatabase: collection_CreateCollection OK for "${collName}"`);
        } catch (e) {
          this.log(
            `Warning: Could not create collection ${collName}: ${e}`,
          );
          this.log(`[DIAG] createDatabase: collection_CreateCollection FAILED for "${collName}": ${JSON.stringify(e)}`);
        }
      }
    } else {
      this.log(`[DIAG] createDatabase: no collections requested`);
    }
    this.log(`[DIAG] createDatabase: done name="${name}" uniqueName="${uniqueName}"`);
  }

  private async loadDataset(
    dbName: string,
    datasetName: string,
  ): Promise<void> {
    const url = tdk.kDatasetBaseURL + datasetName + '/';
    this.log(`[DIAG] loadDataset: start dbName="${dbName}" datasetName="${datasetName}" url="${url}"`);

    const fetchRelative = async (suffix: string): Promise<string> => {
      const fullUrl = url + suffix;
      this.log(`[DIAG] loadDataset: fetching ${fullUrl}`);
      const response = await fetch(fullUrl);
      this.log(`[DIAG] loadDataset: fetch ${suffix} → HTTP ${response.status}`);
      if (response.status !== 200) {
        throw new HTTPError(
          502,
          `Unable to load dataset <${fullUrl}>: ${response.status} ${response.statusText}`,
        );
      }
      return await response.text();
    };

    this.log(`Loading dataset "${datasetName}" into database "${dbName}" from ${url}`);

    this.log(`[DIAG] loadDataset: fetching index.json`);
    const indexText = await fetchRelative('index.json');
    this.log(`[DIAG] loadDataset: index.json text (first 300 chars): ${indexText.substring(0, 300)}`);
    const config = JSON.parse(indexText) as tdk.DatasetIndex;
    if (
      typeof config.name !== 'string' ||
      !Array.isArray(config.collections)
    ) {
      throw new HTTPError(
        400,
        `Not a valid dataset index at <${url}index.json>`,
      );
    }

    this.log(`Dataset index OK: name="${config.name}", collections=[${config.collections.join(', ')}]`);
    this.log(`[DIAG] loadDataset: index parsed — name="${config.name}" collections=${JSON.stringify(config.collections)}`);

    this.log(`[DIAG] loadDataset: calling createDatabase`);
    await this.createDatabase(dbName, config.collections);
    const uniqueName = this.databases.get(dbName)!;
    this.log(`[DIAG] loadDataset: createDatabase done, uniqueName="${uniqueName}"`);

    // Cache blob binaries by digest to avoid redundant network fetches.
    // Swift's blobsFromJsonString expects: { "<path>": { "_type": "blob", "data": { "contentType": "...", "data": [bytes as integers] } } }
    const blobDataCache = new Map<string, Uint8Array>();

    const fetchBlobBinary = async (digest: string): Promise<Uint8Array | null> => {
      if (blobDataCache.has(digest)) {
        this.log(`[DIAG] loadDataset: blob cache HIT digest="${digest}"`);
        return blobDataCache.get(digest)!;
      }
      // Strip "sha1-" prefix and replace "/" with "_" to form the filename.
      const filename = digest.substring(5).replace(/\//g, '_');
      const blobUrl = `https://media.githubusercontent.com/media/couchbaselabs/couchbase-lite-tests/refs/heads/main/dataset/server/dbs/js/${datasetName}/Attachments/${filename}.blob`;
      this.log(`[DIAG] loadDataset: fetching blob digest="${digest}" url="${blobUrl}"`);
      try {
        const resp = await fetch(blobUrl);
        if (resp.status !== 200) {
          this.log(`[DIAG] loadDataset: blob fetch FAILED HTTP=${resp.status} digest="${digest}"`);
          return null;
        }
        const buf = await resp.arrayBuffer();
        const bytes = new Uint8Array(buf);
        blobDataCache.set(digest, bytes);
        this.log(`[DIAG] loadDataset: blob fetched OK digest="${digest}" size=${bytes.byteLength}`);
        return bytes;
      } catch (err: any) {
        this.log(`[DIAG] loadDataset: blob fetch ERROR digest="${digest}" error=${err?.message}`);
        return null;
      }
    };

    let totalDocs = 0;
    for (const collID of config.collections) {
      const {scope, collection} = this.parseCollectionName(collID);
      this.log(`[DIAG] loadDataset: processing collection "${collID}" → scope="${scope}" collection="${collection}"`);

      this.log(`Fetching ${collID}.jsonl from dataset...`);
      const jsonl = await fetchRelative(`${collID}.jsonl`);
      const rawLines = jsonl.trim().split('\n');
      const nonEmptyLines = rawLines.filter(l => l.trim().length > 0);
      this.log(`  ${collID}.jsonl: ${rawLines.length} raw lines, ${nonEmptyLines.length} non-empty`);
      this.log(`[DIAG] loadDataset: [${collID}] first non-empty line sample: ${nonEmptyLines[0]?.substring(0, 120) ?? '(none)'}`);
      if (nonEmptyLines.length === 0) {
        this.log(`  ${collID}: empty .jsonl — 0 docs to load (expected for pull-only collections)`);
      }

      let collDocs = 0;
      let collErrors = 0;
      const isHotels = collID.includes('hotel');

      for (const line of rawLines) {
        if (line.trim().length === 0) {
          continue;
        }
        const docData = JSON.parse(line) as tdk.DatasetDoc;
        const docId = docData._id;
        const body: JSONObject = {...docData};
        delete (body as any)._id;

        const rawBlobs = this.findBlobs(body, url);
        if (isHotels) {
          this.log(`[DIAG] loadDataset: [hotels] saving docId="${docId}" bodyKeys=${JSON.stringify(Object.keys(body))} blobCount=${Object.keys(rawBlobs).length}`);
        }

        // Enrich each blob with binary data in the format Swift's blobsFromJsonString expects:
        // { "_type": "blob", "data": { "contentType": "...", "data": [<byte integers>] } }
        const enrichedBlobs: Record<string, any> = {};
        for (const [blobPath, blobMeta] of Object.entries(rawBlobs)) {
          const digest = blobMeta.digest as string | undefined;
          const contentType = (blobMeta.content_type as string | undefined) ?? 'application/octet-stream';
          if (digest && digest.startsWith('sha1-')) {
            const bytes = await fetchBlobBinary(digest);
            if (bytes !== null) {
              enrichedBlobs[blobPath] = {
                _type: 'blob',
                data: {
                  contentType,
                  data: Array.from(bytes),
                },
              };
              if (isHotels) {
                this.log(`[DIAG] loadDataset: [hotels] blob enriched docId="${docId}" path="${blobPath}" byteLen=${bytes.byteLength}`);
              }
            } else {
              this.log(`[DIAG] loadDataset: [hotels] blob data unavailable docId="${docId}" path="${blobPath}" — skipping blob`);
            }
          }
        }

        try {
          const saveResult = await this.engine.collection_Save({
            id: docId,
            document: JSON.stringify(body),
            blobs: JSON.stringify(enrichedBlobs),
            name: uniqueName,
            scopeName: scope,
            collectionName: collection,
            concurrencyControl: null,
          });
          if (isHotels) {
            this.log(`[DIAG] loadDataset: [hotels] save OK docId="${docId}" result=${JSON.stringify(saveResult)}`);
          }
          collDocs++;
        } catch (saveErr: any) {
          collErrors++;
          this.log(`[DIAG] loadDataset: [${collID}] SAVE ERROR docId="${docId}" error=${JSON.stringify(saveErr)} message=${saveErr?.message}`);
          if (collErrors <= 3) {
            this.log(`Error saving doc "${docId}" in ${collID}: ${saveErr.message}`);
          }
        }
      }

      this.log(`Loaded ${collDocs} docs into ${collID}${collErrors > 0 ? ` (${collErrors} errors)` : ''}`);
      this.log(`[DIAG] loadDataset: [${collID}] SUMMARY — saved=${collDocs} errors=${collErrors} out of ${nonEmptyLines.length} lines`);
      totalDocs += collDocs;
    }

    this.log(`Dataset "${datasetName}" loaded: ${totalDocs} total docs into "${dbName}"`);
    this.log(`[DIAG] loadDataset: done — totalDocs=${totalDocs}`);
  }

  private findBlobs(
    obj: any,
    _datasetURL: string,
  ): Record<string, any> {
    const blobs: Record<string, any> = {};
    const walk = (current: any, pathPrefix: string) => {
      if (Array.isArray(current)) {
        for (let i = 0; i < current.length; i++) {
          walk(current[i], `${pathPrefix}[${i}]`);
        }
      } else if (typeof current === 'object' && current !== null) {
        if (current['@type'] === 'blob') {
          blobs[pathPrefix] = current;
        } else {
          for (const key of Object.keys(current)) {
            const childPath = pathPrefix ? `${pathPrefix}.${key}` : key;
            walk(current[key], childPath);
          }
        }
      }
    };
    walk(obj, '');
    return blobs;
  }

  private extractBlobs(doc: JSONObject): Record<string, any> {
    const blobs: Record<string, any> = {};
    const walk = (obj: any, pathPrefix: string) => {
      if (Array.isArray(obj)) {
        for (let i = 0; i < obj.length; i++) {
          walk(obj[i], `${pathPrefix}[${i}]`);
        }
      } else if (typeof obj === 'object' && obj !== null) {
        if (obj['_type'] === 'blob' && obj.data) {
          blobs[pathPrefix] = obj;
        } else {
          for (const key of Object.keys(obj)) {
            const childPath = pathPrefix ? `${pathPrefix}.${key}` : key;
            walk(obj[key], childPath);
          }
        }
      }
    };
    walk(doc, '');
    return blobs;
  }

  private async downloadBlobMetadata(
    blobURL: string,
  ): Promise<JSONValue> {
    if (blobURL.endsWith('.zip')) {
      throw new HTTPError(501, 'Unzipping blobs is not supported');
    }
    const type = blobURL.endsWith('.jpg')
      ? 'image/jpeg'
      : 'application/octet-stream';
    try {
      let absURL: string;
      if (blobURL.startsWith('http://') || blobURL.startsWith('https://')) {
        absURL = blobURL;
      } else {
        absURL = tdk.kBlobBaseURL + blobURL;
      }
      const response = await fetch(absURL);
      if (response.status !== 200) {
        const status = response.status === 404 ? 400 : 502;
        throw new HTTPError(
          status,
          `Unable to load blob from <${absURL}>: ${response.status} ${response.statusText}`,
        );
      }
      const data = await response.arrayBuffer();
      const bytes = new Uint8Array(data);
      return {
        _type: 'blob',
        data: {
          contentType: type,
          data: Array.from(bytes),
        },
      };
    } catch (e) {
      if (e instanceof HTTPError) {
        throw e;
      }
      throw new HTTPError(400, `Failed to download blob: ${e}`);
    }
  }

  /**
   * Creates a self-contained JavaScript filter function string for the native bridge.
   *
   * The native bridge (iOS JavaScriptCore / Android Rhino) eval's this string for each
   * document during replication. The function receives:
   *   doc   – plain JSON object of the document, with doc.id = document ID
   *   flags – string array, e.g. ["DELETED"] or ["ACCESS_REMOVED"]
   */
  private createFilterFunction(filter: tdk.Filter, collectionName: string): string {
    switch (filter.name) {
      case 'deletedDocumentsOnly':
        return `(function(doc, flags) { return flags.includes('DELETED'); })`;

      case 'documentIDs': {
        const rawParam = filter.params?.documentIDs;
        check(
          isObject(rawParam),
          'documentIDs filter requires a "documentIDs" parameter object',
        );
        const documentIDs = rawParam as Record<string, string[]>;

        // Normalize to scope.collection and look up the allowed IDs for this collection
        const collFullName = collectionIDWithScope(collectionName);
        const ids: string[] =
          (documentIDs[collFullName] as string[] | undefined) ??
          (documentIDs[collectionName] as string[] | undefined) ??
          [];

        check(
          ids.length > 0,
          `documentIDs filter: no IDs found for collection "${collFullName}"`,
        );

        // Embed IDs as a JSON literal — the function must be fully self-contained
        const idsLiteral = JSON.stringify(ids);
        return `(function(doc, flags) { var ids = ${idsLiteral}; return ids.indexOf(doc.id) !== -1; })`;
      }

      default:
        throw new HTTPError(400, `Unknown replicator filter "${filter.name}"`);
    }
  }

  private async getDocumentAsJSON(
    dbName: string,
    scopeName: string,
    collectionName: string,
    docId: string,
    retries = 3,
    retryDelayMs = 1000,
  ): Promise<JSONObject | null> {
    // After a replication event (e.g. re-pull after auto-purge restore), the document
    // may not be committed to the local store immediately. Retry a few times to handle
    // the race between the replicator event and the actual local write.
    for (let attempt = 0; attempt <= retries; attempt++) {
      try {
        const result = await this.engine.collection_GetDocument({
          docId,
          name: dbName,
          scopeName,
          collectionName,
        });
        // Bridge resolves with { _id, _sequence, _data } when found, {} when not found.
        // result.document is never populated by this bridge — use _id as the existence check.
        const r = result as any;
        if (!r || !r._id) {
          if (attempt < retries) {
            await new Promise(resolve => setTimeout(resolve, retryDelayMs));
            continue;
          }
          return null;
        }
        const data = r._data;
        if (!data) {
          return null;
        }
        if (typeof data === 'string') {
          return JSON.parse(data) as JSONObject;
        }
        if (typeof data === 'object') {
          return data as JSONObject;
        }
        return null;
      } catch (_e) {
        if (attempt < retries) {
          await new Promise(resolve => setTimeout(resolve, retryDelayMs));
          continue;
        }
        return null;
      }
    }
    return null;
  }

  private parseCollectionName(fullName: string): {
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
}
