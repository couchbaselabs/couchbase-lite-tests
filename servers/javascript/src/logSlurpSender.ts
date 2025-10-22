import { LogCategory } from "@couchbase/lite-js";
import { WebSocketClient } from "./webSocketClient";
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
            url = new URL(url);
        url.searchParams.append("CBL-Log-ID", id);
        url.searchParams.append("CBL-Log-Tag", tag);
        this.connect(url.toString());
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
