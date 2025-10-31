//
// test/testServer.ts
//
// Copyright 2025-Present Couchbase, Inc.
//
// Use of this software is governed by the Business Source License included
// in the file licenses/BSL-Couchbase.txt.  As of the Change Date specified
// in that file, in accordance with the Business Source License, use of this
// software will be governed by the Apache License, Version 2.0, included in
// the file licenses/APL2.txt.
//

/* eslint-disable camelcase */

import { WebSocketClient } from "./webSocketClient";
import { check } from "./utils";
import * as logtape from "@logtape/logtape";
import * as cbl from "@couchbase/lite-js";


/** States of the TestServer. (Same as the all-caps constants in `WebSocket`.) */
export enum TestServerState {
    Connecting = 0,
    Open,
    Closing,
    Closed
}

export const StateNames = ["connecting", "connected", "closing", "closed"];


/** Initial WebSocket message sent to the WS server upon connecting. */
export interface Hello {
    device      : string;               ///< Same as "CBLTest-Server-ID" response header in spec
    apiVersion  : number;               ///< Same as "CBLTest-API-Version" response header in spec
}


/** Base interface of an incoming JSON request. Actual request interfaces extend this. */
export interface TestRequest {
    readonly ts_id         : number;    ///< Request ID; echoed in the corresponding TestResponse
    readonly ts_clientID?  : string;    ///< Same as "CBLTest-Client-ID" request header in spec
    readonly ts_command    : string;    ///< Same as URI in the API spec
    // (Payload goes here)
}


/** Base interface of a response to a request. (For illustrative purposes only.) */
export interface TestResponse {
    ts_id           : number;
    ts_apiVersion   : number,
    ts_serverID     : string;   ///< Same as "CBLTest-Server-ID" response header in spec
    ts_error?       : {domain: string, code: number, message: string};
    // (Payload goes here)
}


/** An async callback function that handles a specific command. */
export type Handler<RQ extends TestRequest> = (request: RQ) => Promise<object | void>;


/** A simple RPC "server" to let Couchbase Lite QE testing drive Couchbase Lite for JS.
 *  In other platforms this is done by having the app expose an HTTP interface that QE's tests
 *  call, but CBL-JS running in a browser isn't allowed to open listener/server sockets,
 *  so instead we use this backwards "server" that's actually a WebSocket client.
 *  When started it connects to a WebSocket server and sends its client ID.
 *  It then waits for incoming commands, in the form of WebSocket messages containing JSON.
 *
 *  To use this "server":
 *  0. Define a protocol with named commands, each corresponding to an extension of the `Request`
 *     interface and adding any extra parameters needed.
 *  1. Create a new instance, passing it some identifier for this client device.
 *  2. Call `onStateChange` if you want notifications when it connects / disconnects.
 *  3. Call `onCommand` to register handlers for commands identified by strings.
 *     Each handler will be called with an object implementing the `Request` interface.
 *     Handlers are async; your handler should resolve its promise with a JSON-compatible object
 *     containing whatever response parameters are defined for this command.
 *     On failure it should reject the promise (or equivalently, throw an Error.)
 *  4. Call `connect` to connect to the server.
 */
export class TestServer extends WebSocketClient {

    /** The WebSocket protocol ID for TestServer. */
    static kWSProtocol = "CBLTestServer";

    /** The LogTape logger category. */
    static kLoggerCategory = ["TDK", "Server"];

    private serverID: string = crypto.randomUUID();

    /** @param deviceID  This will be sent to the WebSocket server upon connecting,
     *                   so it knows which device this is. */
    constructor(public readonly deviceID: string,
                public readonly apiVersion: number) {
        super(TestServer.kWSProtocol);
    }


    /** Registers a handler function for a particular command string.
     *  Should be called before connecting. */
    onCommand<R extends TestRequest>(command: string, handler: Handler<R>): void {
        check(!this.#handlers.has(command), `Handler for ${command} already registered`);
        this.#handlers.set(command, handler as Handler<TestRequest>);
    }


    /** Registers an object that handles commands.
     *  The object's keys (method names) are command names,
     *  and its values are async functions/methods that take a single parameter extending TestRequest, and return a Promise of either a response object or void. */
    delegate?: object;


    /** Convenience method that sets up LogTape to log to the default JS console. */
    async logToConsole(level: "debug" | "trace" | "info" | "warning" | "error" = "info") {
        await logtape.configure({
            sinks: {
                console: logtape.getConsoleSink(),
            },
            loggers: [
                {
                    category: "TDK",
                    lowestLevel: level,
                    sinks: ["console"],
                },
                {
                    category: cbl.LogCategory,
                    lowestLevel: level,
                    sinks: ["console"],
                },
                {
                    category: ["logtape", "meta"],
                    lowestLevel: "warning",
                    sinks: ["console"],
                }
            ],
            reset: true,
        });
    }


    /** Connects to the server, asynchronously. */
    connect(url: string) {
        this.logger.info `Client ${this.deviceID} connecting to ${url} ...`;
        super.connect(url);
    }


    readonly logger = logtape.getLogger(TestServer.kLoggerCategory);


    /** Closes the connection, asynchronously.. */
    close(code = 1000, reason = "") {
        this.logger.info `Closing WebSocket with code ${code}, reason ${reason}`;
        super.close(code, reason);
    }


    // Internals:


    protected override onOpen() {
        this.logger.info `WebSocket is open! Sending my device ID ${this.deviceID}`;
        const hello: Hello = {device: this.deviceID, apiVersion: this.apiVersion};
        this.send(JSON.stringify(hello));
    }


    protected override onTextMessage(message: string) {
        let request: TestRequest;
        try {
            request = JSON.parse(message) as TestRequest;
        } catch (_x) {
            this.logger.error `Received unparseable request: ${message}`;
            return;
        }
        const {ts_id: id, ts_command: command} = request;
        if (typeof id !== 'number' || typeof command !== 'string' || !command.startsWith('/')) {
            this.logger.error `Received invalid request: ${message}`;
            return;
        }

        let handler;
        if (this.delegate) {
            const delegate = this.delegate as Record<string,Handler<TestRequest>>;
            handler = delegate[command];
            if (typeof handler !== 'function')
                handler = undefined;
            if (handler)
                handler = handler.bind(this.delegate); // sets the 'this' argument
        }

        if (!handler)
            handler = this.#handlers.get(command);

        if (handler) {
            this.logger.info `Received request #${id}, command ${command}`;
            handler(request).then(
                (result) => this.sendResponse(request, result),
                (error: Error)  => this.sendResponse(request, undefined, error)
            );
        } else {
            this.logger.error `No handler registered for command ${command}`;
            this.sendResponse(request, undefined, Error(`Unknown command ${command}`));
        }
    }


    private sendResponse(request: TestRequest, result?: object | void, error?: Error) {
        if (error)
            this.logger.warn `Sending response #${request.ts_id} with error: ${error.message}`;
        else
            this.logger.info `Sending response #${request.ts_id}`;
        const response: TestResponse = {ts_id: request.ts_id, ts_serverID: this.serverID, ts_apiVersion: this.apiVersion, ...result};
        if (error) {
            const code = (error instanceof HTTPError) ? error.code : -1;
            response.ts_error = {domain: error.name, code: code, message: error.message};
        }
        this.send(JSON.stringify(response));
    }


    protected override onClose() {
        if (this.error)
            this.logger.error(this.error);
    }


    #handlers   = new Map<string,Handler<TestRequest>>();
}
