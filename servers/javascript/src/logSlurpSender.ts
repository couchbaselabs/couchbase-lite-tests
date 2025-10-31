import { LogCategory } from "@couchbase/lite-js";
import { WebSocketClient, WebSocketState } from "./webSocketClient";
import * as logtape from "@logtape/logtape";


export class LogSlurpSender extends WebSocketClient implements Disposable {
    constructor(url: URL | string,
                id: string,
                readonly tag: string)
    {
        super();

        this.#sinkID = `LogSender-${tag}`;
        let config = logtape.getConfig()!;
        config.sinks[this.#sinkID] = (record) => this.sendLog(record);
        for (let logger of config.loggers) {
            if (logger.category !== "logtape" &&
                    !(Array.isArray(logger.category) && logger.category[0] === "logtape")) {
                logger.sinks?.push(this.#sinkID);
            }
        }
        logtape.configureSync(config);

        if (typeof url === 'string')
            url = new URL(`ws://${url}/openLogStream`);

        url.searchParams.append("cbl_log_id", id);
        url.searchParams.append("cbl_log_tag", tag);
        this.connect(url.toString());
    }

    async waitForConnected(timeoutMs?: number): Promise<void> {
        if (this.isOpen) return;
        if (this.state === WebSocketState.Closed)
            throw new Error(this.error ?? "WebSocket already closed");
        return new Promise<void>((resolve, reject) => {
            const prev = this.onStateChange;
            let done = false;
            let timer: number | NodeJS.Timeout | undefined;
            const finish = (fn: () => void) => {
                if (done) return;
                done = true;
                if (timer) clearTimeout(timer);
                this.onStateChange = prev;
                fn();
            };
            this.onStateChange = (state) => {
                prev?.(state);
                if (state === WebSocketState.Open)
                    finish(resolve);
                else if (state === WebSocketState.Closed || state === WebSocketState.Closing)
                    finish(() => reject(new Error(this.error ?? "WebSocket closed before opening")));
            };
            if (timeoutMs)
                timer = setTimeout(() => finish(() => reject(new Error("Timeout waiting for WebSocket open"))), timeoutMs);
        });
    }

    stopLogging() {
        let config = logtape.getConfig()!;
        for (let logger of config.loggers) {
            const i = logger.sinks?.indexOf(this.#sinkID);
            if (i !== undefined && i >= 0)
                logger.sinks?.splice(i, 1);
        }
        delete config.sinks[this.#sinkID];
    }


    close(code = 1000, reason = "") {
        this.stopLogging();
        super.close(code, reason);
    }


    private sendLog(record: logtape.LogRecord) {
        let category = record.category;
        if (category[0] === LogCategory)
            category = category.slice(1);
        const message = `[${category.join(".")}] ${record.message.join("")}`;

        if (this.isOpen)
            this.send(message);
        else if (this.#buffer)
            this.#buffer.push(message);
    }


    protected override onOpen() {
        for (const message of this.#buffer!)
            this.send(message);
        this.#buffer = undefined;
    }


    protected override onClose() {
        this.stopLogging();
        this.#buffer = undefined;
    }

    readonly #sinkID    : string;
    #buffer?            : string[] = [];
}
