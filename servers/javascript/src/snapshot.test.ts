import {Snapshot} from "./snapshot";
import { indexedDB, IDBKeyRange } from "fake-indexeddb";
import * as cbl from "@couchbase/lite-js";
import { beforeEach, test, describe, expect, afterEach } from "vitest";


cbl.Database.useIndexedDB(indexedDB, IDBKeyRange);


let db!: cbl.Database;
let red!: cbl.Collection;

beforeEach( async() => {
    db = await cbl.Database.open({
        name: "snapshotTest",
        version: 1,
        collections: {red: {}}
    });
    red = db.getCollection("red");
});

afterEach( async() => {
    await db?.closeAndDelete();
});


describe("Snapshot", () => {

    test("doc wasn't created", async () => {
        const snapshot = new Snapshot(db);
        await snapshot.record("red", cbl.DocID("nose"));

        const response = await snapshot.verify([{
            type: 'UPDATE',
            collection: "red",
            documentID: cbl.DocID("nose"),
        }]);
        expect(response).toMatchInlineSnapshot(`
          {
            "description": "Document nose in collection red was not found",
            "document": undefined,
            "result": false,
          }
        `);
    });


    test("doc was created", async () => {
        const snapshot = new Snapshot(db);
        await snapshot.record("red", cbl.DocID("nose"));

        await red.save(red.createDocument(cbl.DocID("nose"), {
            name: "Santa",
            reindeer: ["Dasher", "Prancer", "etc."],
        }));

        const response = await snapshot.verify([{
            collection: "red",
            documentID: cbl.DocID("nose"),
            type: 'UPDATE',
            updatedProperties: [{
                name: "Santa",
                reindeer: ["Dasher", "Prancer", "etc."],
            }],
        }]);
        expect(response).toEqual({result: true});
    });


    test("doc was deleted", async () => {
        const nose = red.createDocument(cbl.DocID("nose"), {
            name: "Santa",
            reindeer: ["Dasher", "Prancer", "etc."],
        });
        await red.save(nose);

        const snapshot = new Snapshot(db);
        await snapshot.record("red", cbl.DocID("nose"));

        await red.delete(nose);

        const response = await snapshot.verify([{
            collection: "red",
            documentID: cbl.DocID("nose"),
            type: 'DELETE',
        }]);
        expect(response).toEqual({result: true});
    });


    test("doc was not deleted", async () => {
        const nose = red.createDocument(cbl.DocID("nose"), {
            name: "Santa",
            reindeer: ["Dasher", "Prancer", "etc."],
        });
        await red.save(nose);

        const snapshot = new Snapshot(db);
        await snapshot.record("red", cbl.DocID("nose"));

        const response = await snapshot.verify([{
            collection: "red",
            documentID: cbl.DocID("nose"),
            type: 'DELETE',
        }]);
        expect(response).toEqual({
            "result": false,
            "description": "Document nose in collection red was not deleted",
            "document": {
                "name": "Santa",
                "reindeer": [
                    "Dasher",
                    "Prancer",
                    "etc.",
                ],
            },
        });
    });


    test("doc was created with wrong properties", async () => {
        const snapshot = new Snapshot(db);
        await snapshot.record("red", cbl.DocID("nose"));

        await red.save(red.createDocument(cbl.DocID("nose"), {
            name: "Santa",
            reindeer: ["Dasher", "Prancer", "Rudolph"],
        }));

        const response = await snapshot.verify([{
            collection: "red",
            documentID: cbl.DocID("nose"),
            type: 'UPDATE',
            updatedProperties: [{
                name: "Santa",
                reindeer: ["Dasher", "Prancer", "etc."],
            }],
        }]);

        expect(response).toEqual({
            "result": false,
            "description": "Document nose in collection red had unexpected properties at .reindeer[2]",
            "expected": "etc.",
            "actual": "Rudolph",
            "document": {
                "name": "Santa",
                "reindeer": [
                    "Dasher",
                    "Prancer",
                    "Rudolph",
                ],
            },
        });
    });


    test("doc was modified", async () => {
        const nose = red.createDocument(cbl.DocID("nose"), {
            name: "Santa",
            reindeer: ["Dasher", "Prancer", "etc."],
        });
        await red.save(nose);

        const snapshot = new Snapshot(db);
        await snapshot.record("red", cbl.DocID("nose"));

        (nose.reindeer as string[])[2] = "Rudolph";

        const response = await snapshot.verify([{
            collection: "red",
            documentID: cbl.DocID("nose"),
            type: 'UPDATE',
            updatedProperties: [{
                "reindeer[2]": "Rudolph",
            }],
        }]);

        expect(response).toEqual({
            "result": false,
            "description": "Document nose in collection red had unexpected properties at .reindeer[2]",
            "expected": "Rudolph",
            "actual": "etc.",
            "document": {
                "name": "Santa",
                "reindeer": [
                    "Dasher",
                    "Prancer",
                    "etc.",
                ],
            },
        });
    });


    test("doc was not modified", async () => {
        const snapshot = new Snapshot(db);

        const nose = red.createDocument(cbl.DocID("nose"), {
            name: "Santa",
            reindeer: ["Dasher", "Prancer", "etc."],
        });
        await red.save(nose);

        await snapshot.record("red", cbl.DocID("nose"));

        const response = await snapshot.verify([{
            collection: "red",
            documentID: cbl.DocID("nose"),
            type: 'UPDATE',
            updatedProperties: [{
                "reindeer[2]": "Rudolph",
            }],
        }]);

        expect(response).toEqual({
            "result": false,
            "description": "Document nose in collection red had unexpected properties at .reindeer[2]",
            "expected": "Rudolph",
            "actual": "etc.",
            "document": {
                "name": "Santa",
                "reindeer": [
                    "Dasher",
                    "Prancer",
                    "etc.",
                ],
            },
        });
    });

});
