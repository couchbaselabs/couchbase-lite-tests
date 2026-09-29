// WebSocket client base class for React Native.
// Adapted from the JavaScript server's webSocketClient.ts to use RN's built-in WebSocket.
//
// Copyright 2025-Present Couchbase, Inc.
//
// Use of this software is governed by the Business Source License included
// in the file licenses/BSL-Couchbase.txt.  As of the Change Date specified
// in that file, in accordance with the Business Source License, use of this
// software will be governed by the Apache License, Version 2.0, included in
// the file licenses/APL2.txt.

export enum WebSocketState {
  Connecting = 0,
  Open,
  Closing,
  Closed,
}

export const WebSocketStateNames = [
  'connecting',
  'connected',
  'closing',
  'closed',
];

export abstract class WebSocketClient {
  private ws?: WebSocket;
  private errorMessage?: string;
  private wasOpen = false;
  private subProtocol?: string;

  onStateChange?: (state: WebSocketState) => void;

  constructor(subProtocol?: string) {
    this.subProtocol = subProtocol;
  }

  get state(): WebSocketState {
    if (!this.ws) {
      return WebSocketState.Closed;
    }
    return this.ws.readyState as WebSocketState;
  }

  get isOpen(): boolean {
    return this.state === WebSocketState.Open;
  }

  get error(): string | undefined {
    return this.errorMessage;
  }

  connect(url: string): void {
    // RN's WebSocket accepts protocols as second arg (string or string[])
    if (this.subProtocol) {
      this.ws = new WebSocket(url, this.subProtocol);
    } else {
      this.ws = new WebSocket(url);
    }

    this.ws.onopen = () => this.handleWSOpen();
    this.ws.onmessage = (event) => this.handleWSMessage(event);
    this.ws.onclose = (event) => this.handleWSClose(event);
    this.ws.onerror = () => this.handleWSError();

    this.onStateChange?.(this.state);
  }

  close(code = 1000, reason = ''): void {
    if (this.ws) {
      this.ws.close(code, reason);
      this.onStateChange?.(this.state);
    }
  }

  dispose(): void {
    this.close();
  }

  protected onOpen(): void {}

  protected send(message: string): void {
    if (!this.ws) {
      throw new Error('WebSocket is closed');
    }
    this.ws.send(message);
  }

  protected onTextMessage(_message: string): void {}

  protected onClose(): void {}

  private handleWSOpen(): void {
    this.wasOpen = true;
    this.onOpen();
    this.onStateChange?.(this.state);
  }

  private handleWSMessage(event: {data?: string | ArrayBuffer | Blob}): void {
    if (typeof event.data === 'string') {
      this.onTextMessage(event.data);
    }
  }

  private handleWSClose(event: {code?: number; reason?: string}): void {
    if (event.code !== undefined && event.code !== 1000) {
      let message = `WebSocket closed unexpectedly with code ${event.code}`;
      if (event.reason) {
        message += `: ${event.reason}`;
      }
      this.errorMessage = message;
    }
    this.closed();
  }

  private handleWSError(): void {
    this.errorMessage = this.wasOpen
      ? 'WebSocket disconnected'
      : 'WebSocket connection failed';
    this.closed();
  }

  private closed(): void {
    this.wasOpen = false;
    this.ws = undefined;
    this.onClose();
    this.onStateChange?.(this.state);
  }
}
