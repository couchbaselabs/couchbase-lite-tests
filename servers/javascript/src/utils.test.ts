import { ReplicatorError } from "@couchbase/lite-js";
import { describe, expect, test } from "vitest";
import { errorInfo } from "./utils";

// CBL JS does not export these classes, so the fakes copy the name and properties it sets.
function blipError(name: string, code: number, message = "BLIP error"): Error {
    return Object.assign(new Error(message), { name, blipErrorCode: code, blipErrorDomain: "HTTP" });
}

function webSocketError(code: number, message = "WebSocket error"): Error {
    return Object.assign(new Error(message), { name: "WebSocketError", code });
}

describe("errorInfo", () => {
    test("no error", () => {
        expect(errorInfo(undefined)).toBeUndefined();
    });

    test("a status or close code maps to CBL/10000+code", () => {
        const testCases: Array<[Error, number]> = [
            [blipError("blip.MessageError", 403, "Peer responded with error: pull-only"), 10403],
            [new ReplicatorError("Peer responded with error", 409, blipError("blip.MessageError", 409)), 10409],
            [new ReplicatorError("Authentication failed; username or password not valid.", 401), 10401],
            [new ReplicatorError("Authentication failed. [404 Not Found]", 404), 10404],
            [new ReplicatorError("Collection 'travel.hotels' does not exist on the server", 404), 10404],
            [
                new ReplicatorError("Server connection failed; [NetworkError]", 502, new TypeError("NetworkError")),
                10502,
            ],
            [blipError("blip.BLIPError", 400, "invalid revision body"), 10400],
            [webSocketError(1008, "Policy violation"), 11008],
        ];
        for (const [error, code] of testCases) {
            expect(errorInfo(error), error.message).toEqual({ domain: "CBL", code, message: error.message });
        }
    });

    test("any other error maps to CBL-JS/-1", () => {
        const testCases: Error[] = [
            new ReplicatorError("Connection is closed", -1, blipError("blip.BLIPError", -1)),
            webSocketError(1005, "Failed to connect (no information available)"),
            webSocketError(1006, "Unexpected disconnect (no information available)"),
            webSocketError(1000, "BLIP connection closed unexpectedly"),
            new Error("Assertion failed: nextSequence must be called in a transaction is unexpectedly undefined"),
        ];
        for (const error of testCases) {
            expect(errorInfo(error), error.message).toEqual({ domain: "CBL-JS", code: -1, message: error.message });
        }
    });
});
