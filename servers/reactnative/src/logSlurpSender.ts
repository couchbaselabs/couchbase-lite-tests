// LogSlurp WebSocket sender for React Native.
// Adapted from the JavaScript server's logSlurpSender.ts.
//
// Copyright 2025-Present Couchbase, Inc.
//
// Use of this software is governed by the Business Source License included
// in the file licenses/BSL-Couchbase.txt.  As of the Change Date specified
// in that file, in accordance with the Business Source License, use of this
// software will be governed by the Apache License, Version 2.0, included in
// the file licenses/APL2.txt.

import {WebSocketClient, WebSocketState} from './webSocketClient';

export class LogSlurpSender extends WebSocketClient {
  private buffer: string[] | undefined = [];
  private logging = true;

  constructor(
    url: string,
    id: string,
    readonly tag: string,
  ) {
    super();

    let wsUrl: string;
    if (url.startsWith('ws://') || url.startsWith('wss://')) {
      wsUrl = `${url}/openLogStream?cbl_log_id=${encodeURIComponent(id)}&cbl_log_tag=${encodeURIComponent(tag)}`;
    } else {
      wsUrl = `ws://${url}/openLogStream?cbl_log_id=${encodeURIComponent(id)}&cbl_log_tag=${encodeURIComponent(tag)}`;
    }

    this.connect(wsUrl);
  }

  async waitForConnected(timeoutMs?: number): Promise<void> {
    if (this.isOpen) {
      return;
    }
    if (this.state === WebSocketState.Closed) {
      throw new Error(this.error ?? 'WebSocket already closed');
    }
    return new Promise<void>((resolve, reject) => {
      const prev = this.onStateChange;
      let done = false;
      let timer: ReturnType<typeof setTimeout> | undefined;
      const finish = (fn: () => void) => {
        if (done) {
          return;
        }
        done = true;
        if (timer) {
          clearTimeout(timer);
        }
        this.onStateChange = prev;
        fn();
      };
      this.onStateChange = state => {
        prev?.(state);
        if (state === WebSocketState.Open) {
          finish(resolve);
        } else if (
          state === WebSocketState.Closed ||
          state === WebSocketState.Closing
        ) {
          finish(() =>
            reject(
              new Error(this.error ?? 'WebSocket closed before opening'),
            ),
          );
        }
      };
      if (timeoutMs) {
        timer = setTimeout(
          () =>
            finish(() =>
              reject(new Error('Timeout waiting for WebSocket open')),
            ),
          timeoutMs,
        );
      }
    });
  }

  sendLogMessage(message: string): void {
    if (!this.logging) {
      return;
    }
    if (this.isOpen) {
      this.send(message);
    } else if (this.buffer) {
      this.buffer.push(message);
    }
  }

  stopLogging(): void {
    this.logging = false;
    this.buffer = undefined;
  }

  close(code = 1000, reason = ''): void {
    this.stopLogging();
    super.close(code, reason);
  }

  protected override onOpen(): void {
    if (this.buffer) {
      for (const message of this.buffer) {
        this.send(message);
      }
      this.buffer = undefined;
    }
  }

  protected override onClose(): void {
    this.stopLogging();
  }
}
