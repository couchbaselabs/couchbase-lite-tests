//
// test/webSocketClient.ts
//
// Copyright 2025-Present Couchbase, Inc.
//
// Use of this software is governed by the Business Source License included
// in the file licenses/BSL-Couchbase.txt.  As of the Change Date specified
// in that file, in accordance with the Business Source License, use of this
// software will be governed by the Apache License, Version 2.0, included in
// the file licenses/APL2.txt.
//

import { check } from "./httpError";


/** States of WebSocketClient. (Same as the all-caps constants in `WebSocket`.) */
export enum WebSocketState {
    Connecting = 0,
    Open,
    Closing,
    Closed
}


export const WebSocketStateNames = ["connecting", "connected", "closing", "closed"];


/** Simple WebSocket client class, used by TestServer and LogSender. */
export abstract class WebSocketClient implements Disposable {
    constructor(private subProtocol?: string) { }

    /** A callback that notifies about state changes. */
    onStateChange? : (state: WebSocketState)=>void;


    /** Connects to the server, asynchronously. */
    connect(url: string) {
        this.#ws = new WebSocket(url, this.subProtocol);
        this.#ws.onopen     = ()      => {this.handleWSOpen();};
        this.#ws.onmessage  = (event) => {this.handleWSMessage(event);};
        this.#ws.onclose    = (event) => {this.handleWSClose(event);};
        this.#ws.onerror    = (event) => {this.handleWSError(event);};
        this.onStateChange?.(this.state);
    }


    /** The WebSocket's current state. */
    get state() : WebSocketState { return this.#ws?.readyState ?? WebSocketState.Closed; }

    get isOpen() : boolean {return this.state === WebSocketState.Open;}

    /** The connection error, if any. */
    get error() : string | undefined {return this.#errorMessage;}


    /** Closes the connection, asynchronously.. */
    close(code = 1000, reason = "") {
        if (this.#ws) {
            check(code >= 1000, "Error code must be >= 1000");
            this.#ws.close(code, reason);
            this.onStateChange?.(this.state);
        }
    }

    [Symbol.dispose]() {this.close();}


    //-------- For subclasses:


    protected onOpen() { }

    protected send(message: string) {
        check(this.#ws !== undefined, "WebSocket is closed");
        this.#ws.send(message);
    }

    protected onTextMessage(_message: string) { }

    protected onClose() { }


    //------- Internal:


    private handleWSOpen() {
        check(this.#ws !== undefined, "WebSocket is closed");
        // Commented out because `protocol` is always an empty string in node.js; maybe it works in a browser?
        // if (this.#ws.protocol !== this.subProtocol) {
        //     this.#logger.error `WebSocket is open, but protocol is ${this.#ws?.protocol}`;
        //     this.#logger.error `WebSocket server does not support protocol ${this.subProtocol}; closing`;
        //     this.close(3000, "Protocol not supported");
        //     return;
        // }

        this.#open = true;
        this.onOpen();
        this.onStateChange?.(this.state);
    }


    private handleWSMessage(event: MessageEvent) {
        if (typeof event.data === 'string')
            this.onTextMessage(event.data);
    }


    private handleWSClose(event: CloseEvent) {
        if (event.code !== 1000 || !event.wasClean) {
            let message = `WebSocket closed unexpectedly with code ${event.code}`;
            if (event.reason)
                message += `: ${event.reason}`;
            this.#errorMessage = message;
        }
        this.closed();
    }


    private handleWSError(_event: Event) {
        // In a browser there is, unfortunately, no useful information in the ErrorEvent.
        this.#errorMessage = this.#open ? "WebSocket disconnected" : "WebSocket connection failed";
        this.closed();
    }


    private closed() {
        this.#open = false;
        this.#ws = undefined;
        this.onClose();
        this.onStateChange?.(this.state);
    }


    #ws?            : WebSocket;
    #errorMessage?  : string;
    #open           = false;
}
