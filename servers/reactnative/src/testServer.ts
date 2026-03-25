// Test server: WebSocket client + command dispatcher for React Native.
// Adapted from the JavaScript server's testServer.ts.
//
// Copyright 2025-Present Couchbase, Inc.
//
// Use of this software is governed by the Business Source License included
// in the file licenses/BSL-Couchbase.txt.  As of the Change Date specified
// in that file, in accordance with the Business Source License, use of this
// software will be governed by the Apache License, Version 2.0, included in
// the file licenses/APL2.txt.

import {WebSocketClient} from './webSocketClient';
import uuid from 'react-native-uuid';

// Lifecycle states of the WebSocket connection.
export enum TestServerState {
  Connecting = 0,
  Open,
  Closing,
  Closed,
}

export const StateNames = ['connecting', 'connected', 'closing', 'closed'];

// First message sent to the test runner after the WebSocket opens.
// Tells the runner which device this is and which API version it supports.
export interface Hello {
  device: string;
  apiVersion: number;
}

// Incoming command sent by the test runner over WebSocket (JSON).
// ts_id ties the request to its reply; ts_command is the route e.g. "/reset".
export interface TestRequest {
  readonly ts_id: number;
  readonly ts_clientID?: string;
  readonly ts_command: string;
  [key: string]: any;
}

// Reply (response) sent back to the test runner after handling a request.
// Always echoes ts_id so the runner can match it to the original request.
// ts_error is only present when something went wrong.
export interface TestResponse {
  ts_id: number;
  ts_apiVersion: number;
  ts_serverID: string;
  ts_error?: {domain: string; code: number; message: string};
  [key: string]: any;
}

// A function (handler) that receives a request and returns a result — or nothing.
export type Handler<RQ extends TestRequest> = (
  request: RQ,
) => Promise<object | void>;

/**
 * Connects (via WebSocket) to a test runner and routes (sends/receives)
 * JSON commands to registered handler functions.
 *
 * Build it with:
 *   new TestServer("android-pixel-7", 1)
 *
 * Wire format — what travels over the socket:
 *   Sends on open : { device: string, apiVersion: number }
 *   Receives      : { ts_id: number, ts_command: string, ...payload }
 *   Sends back    : { ts_id, ts_serverID, ts_apiVersion, ...result }
 *                   or { ts_error: { domain, code, message } } on failure
 */
export class TestServer extends WebSocketClient {
  static kWSProtocol = 'CBLTestServer';

  private serverID: string = uuid.v4() as string;
  // Lookup table: command string (e.g. "/reset") → its handler function.
  private handlers = new Map<string, Handler<TestRequest>>();

  public readonly deviceID: string;
  public readonly apiVersion: number;

  delegate?: object;

  onLog?: (message: string) => void;

  // deviceID  — unique name for this device, sent to the runner on connect.
  // apiVersion — version number included in every response frame.
  constructor(deviceID: string, apiVersion: number) {
    super(TestServer.kWSProtocol);
    this.deviceID = deviceID;
    this.apiVersion = apiVersion;
  }

  private log(message: string): void {
    console.log(`[TestServer] ${message}`);
    this.onLog?.(`[TestServer] ${message}`);
  }

  // Registers (saves) a handler for a given command string.
  // Throws if the same command is registered (added) twice.
  onCommand<R extends TestRequest>(
    command: string,
    handler: Handler<R>,
  ): void {
    if (this.handlers.has(command)) {
      throw new Error(`Handler for ${command} already registered`);
    }
    this.handlers.set(command, handler as Handler<TestRequest>);
  }

  connect(url: string): void {
    this.log(`Client ${this.deviceID} connecting to ${url} ...`);
    super.connect(url);
  }

  close(code = 1000, reason = ''): void {
    this.log(`Closing WebSocket with code ${code}, reason ${reason}`);
    super.close(code, reason);
  }

  // Called when the socket opens. Sends the Hello frame (handshake) to the runner.
  protected override onOpen(): void {
    this.log(`WebSocket is open! Sending device ID ${this.deviceID}`);
    const hello: Hello = {
      device: this.deviceID,
      apiVersion: this.apiVersion,
    };
    this.send(JSON.stringify(hello));
  }

  // Receives a raw JSON string, parses it into a TestRequest,
  // finds (looks up) the right handler, runs it, then sends the response.
  protected override onTextMessage(message: string): void {
    let request: TestRequest;
    try {
      request = JSON.parse(message) as TestRequest;
    } catch (_x) {
      this.log(`Received unparseable request: ${message.substring(0, 200)}`);
      return;
    }

    const {ts_id: id, ts_command: command} = request;
    if (
      typeof id !== 'number' ||
      typeof command !== 'string' ||
      !command.startsWith('/')
    ) {
      this.log(`Received invalid request: ${message.substring(0, 200)}`);
      return;
    }

    let handler: Handler<TestRequest> | undefined;

    if (this.delegate) {
      const delegate = this.delegate as Record<
        string,
        Handler<TestRequest>
      >;
      const fn = delegate[command];
      if (typeof fn === 'function') {
        handler = fn.bind(this.delegate);
      }
    }

    if (!handler) {
      handler = this.handlers.get(command);
    }

    if (handler) {
      this.log(`Received request #${id}, command ${command}`);
      handler(request).then(
        result => this.sendResponse(request, result),
        (error: Error) => this.sendResponse(request, undefined, error),
      );
    } else {
      this.log(`No handler registered for command ${command}`);
      this.sendResponse(
        request,
        undefined,
        new Error(`Unknown command ${command}`),
      );
    }
  }

  // Builds (assembles) a TestResponse from the request id, server metadata,
  // and the handler result — then sends it as JSON over the socket.
  // If an error is passed, attaches ts_error instead of a result payload.
  private sendResponse(
    request: TestRequest,
    result?: object | void,
    error?: Error,
  ): void {
    if (error) {
      this.log(
        `Sending response #${request.ts_id} with error: ${error.message}`,
      );
    } else {
      this.log(`Sending response #${request.ts_id}`);
    }

    const response: TestResponse = {
      ts_id: request.ts_id,
      ts_serverID: this.serverID,
      ts_apiVersion: this.apiVersion,
      ...result,
    };

    if (error) {
      const domain =
        'domain' in error && typeof (error as any).domain === 'string'
          ? (error as any).domain
          : error.name;
      const code =
        'code' in error && typeof (error as any).code === 'number'
          ? (error as any).code
          : -1;
      response.ts_error = {domain, code, message: error.message};
    }

    this.send(JSON.stringify(response));
  }

  protected override onClose(): void {
    if (this.error) {
      this.log(`Connection error: ${this.error}`);
    }
  }
}
