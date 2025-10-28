import {Snapshot} from "./snapshot";
import { indexedDB, IDBKeyRange } from "fake-indexeddb";
import * as cbl from "@couchbase/lite-js";
import { beforeEach, test, describe, expect, afterEach } from "vitest";


/* eslint-disable @typescript-eslint/require-await */

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


async function noBlobLoader(_url: string): Promise<cbl.NewBlob> {
    throw Error("Should not be called");
}


describe("Snapshot", () => {

    test("doc wasn't created", async () => {
        const snapshot = new Snapshot(db);
        await snapshot.record("red", cbl.DocID("nose"));

        const response = await snapshot.verify([{
            type: 'UPDATE',
            collection: "red",
            documentID: cbl.DocID("nose"),
        }], noBlobLoader);
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
        }], noBlobLoader);
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
        }], noBlobLoader);
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
        }], noBlobLoader);
        expect(response).toEqual({
            "result": false,
            "description": "Document nose in collection red was not deleted"
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
        }], noBlobLoader);

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
        await red.save(nose);

        const response = await snapshot.verify([{
            collection: "red",
            documentID: cbl.DocID("nose"),
            type: 'UPDATE',
            updatedProperties: [{
                "reindeer[2]": "Rudolph",
            }],
        }], noBlobLoader);

        expect(response).toEqual({"result": true});
    });


    test("doc added a blob", async () => {
        const nose = red.createDocument(cbl.DocID("nose"), {
            name: "Santa",
            reindeer: ["Dasher", "Prancer", "etc."],
        });
        await red.save(nose);

        const snapshot = new Snapshot(db);
        await snapshot.record("red", cbl.DocID("nose"));

        const hohoho = new TextEncoder().encode("Ho ho ho!");
        nose.hohoho = new cbl.NewBlob(hohoho, "text/plain");
        await red.save(nose);

        const blobLoader = async (url: string): Promise<cbl.NewBlob> => {
            expect(url).toBe("x/y/hohoho.txt");
            return new cbl.NewBlob(hohoho, "text/plain");
        };

        const response = await snapshot.verify([{
            collection: "red",
            documentID: cbl.DocID("nose"),
            type: 'UPDATE',
            updatedBlobs: {
                "hohoho": "x/y/hohoho.txt",
            },
        }], blobLoader);

        expect(response).toEqual({"result": true});
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
        }], noBlobLoader);

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
