import type { JSONValue } from "@couchbase/lite-js";
import {KeyPath} from "./keyPath";
import { test, describe, expect } from "vitest";


describe("KeyPath", () => {

    test("Path parsing", () => {
        const testCases: Record<string,Array<string|number>> = {
            "foo": ["foo"],
            "$.foo": ["foo"],
            "foo[3]": ["foo", 3],
            "a.b.c": ["a", "b", "c"],
            "a[12].b[-7]": ["a", 12, "b", -7],
            "a[1][2][3]": ["a", 1, 2, 3],
            "[12].z": [12, "z"],
        };
        for (const pathStr of Object.getOwnPropertyNames(testCases)) {
            let path = new KeyPath(pathStr);
            expect(path.components).toEqual(testCases[pathStr]);
        }
    });

    test("Path parsing failure", () => {
        const testCases = [
            "",
            "$.",
            "x..y",
            "[1z]",
            "[1.5]",
            "[1",
        ];
        for (const pathStr of testCases) {
            expect( () => new KeyPath(pathStr) ).toThrow();
        }
    });

    test("Path reading", () => {
        const object = {
            arr: [1, 2, 3, [4, 5]],
            obj: {a: "A", b: "B", c: {d: "D"}},
        };

        expect(KeyPath.read(object, "[0]")).toBe(undefined);
        expect(KeyPath.read(object, "foo.bar")).toBe(undefined);
        expect(KeyPath.read(object, "arr")).toBe(object.arr);
        expect(KeyPath.read(object, "arr[0]")).toBe(1);
        expect(KeyPath.read(object, "arr[999]")).toBe(undefined);
        expect(KeyPath.read(object, "arr[3][0]")).toBe(4);

        expect(KeyPath.read(object, "obj")).toBe(object.obj);
        expect(KeyPath.read(object, "obj.a")).toBe("A");
        expect(KeyPath.read(object, "obj.a.b")).toBe(undefined);
        expect(KeyPath.read(object, "obj.a[0]")).toBe(undefined);
        expect(KeyPath.read(object, "obj.c.d")).toBe("D");
    });

    test("Path writing", () => {
        function update(pathStr: string, value: JSONValue | undefined): string | undefined {
            const object = {
                arr: [0, 1, 2, 3, [4, 5]],
                obj: {a: "A", b: "B", c: {d: "D"}},
            };
            if (KeyPath.write(object, pathStr, value))
                return JSON.stringify(object);
            else
                return undefined;
        }
        expect(update("obj.a", "BAR")).toMatchInlineSnapshot(`"{"arr":[0,1,2,3,[4,5]],"obj":{"a":"BAR","b":"B","c":{"d":"D"}}}"`);
        expect(update("obj.c", "BAR")).toMatchInlineSnapshot(`"{"arr":[0,1,2,3,[4,5]],"obj":{"a":"A","b":"B","c":"BAR"}}"`);
        expect(update("obj.x[1]", "BAR")).toMatchInlineSnapshot(`"{"arr":[0,1,2,3,[4,5]],"obj":{"a":"A","b":"B","c":{"d":"D"},"x":[null,"BAR"]}}"`);

        expect(update("foo", "BAR")).toMatchInlineSnapshot(`"{"arr":[0,1,2,3,[4,5]],"obj":{"a":"A","b":"B","c":{"d":"D"}},"foo":"BAR"}"`);
        expect(update("foo.bar.baz", "BAR")).toMatchInlineSnapshot(`"{"arr":[0,1,2,3,[4,5]],"obj":{"a":"A","b":"B","c":{"d":"D"}},"foo":{"bar":{"baz":"BAR"}}}"`);

        expect(update("arr[0]", "BAR")).toMatchInlineSnapshot(`"{"arr":["BAR",1,2,3,[4,5]],"obj":{"a":"A","b":"B","c":{"d":"D"}}}"`);
        expect(update("arr[6]", "BAR")).toMatchInlineSnapshot(`"{"arr":[0,1,2,3,[4,5],null,"BAR"],"obj":{"a":"A","b":"B","c":{"d":"D"}}}"`);
        expect(update("arr[4][0]", "BAR")).toMatchInlineSnapshot(`"{"arr":[0,1,2,3,["BAR",5]],"obj":{"a":"A","b":"B","c":{"d":"D"}}}"`);

        expect(update("arr[0]", undefined)).toMatchInlineSnapshot(`"{"arr":[1,2,3,[4,5]],"obj":{"a":"A","b":"B","c":{"d":"D"}}}"`);
        expect(update("arr[4]", undefined)).toMatchInlineSnapshot(`"{"arr":[0,1,2,3],"obj":{"a":"A","b":"B","c":{"d":"D"}}}"`);
        expect(update("obj", undefined)).toMatchInlineSnapshot(`"{"arr":[0,1,2,3,[4,5]]}"`);
        expect(update("obj.z", undefined)).toMatchInlineSnapshot(`"{"arr":[0,1,2,3,[4,5]],"obj":{"a":"A","b":"B","c":{"d":"D"}}}"`);

        expect(update("[12]", "BAR")).toBeUndefined();
        expect(update("arr.x", "BAR")).toBeUndefined();
        expect(update("arr[0].x", "BAR")).toBeUndefined();
        expect(update("arr[0][1]", "BAR")).toBeUndefined();
        expect(update("obj.a.b", "BAR")).toBeUndefined();
        expect(update("obj.a[0]", "BAR")).toBeUndefined();
    });
});
