using Couchbase.Lite;
using System;
using System.Diagnostics;
using System.Dynamic;
using System.Linq;
using System.Net;
using System.Text.Json;
using System.Text.Json.Serialization;
using TestServer.Utilities;

namespace TestServer.Handlers;

internal static partial class HandlerList
{
    internal readonly record struct VerifyDocumentsBody
    {
        public required string database { get; init; }

        public required string snapshot { get; init; }

        public required IReadOnlyList<UpdateDatabaseEntry> changes { get; init; }

        [JsonConstructor]
        public VerifyDocumentsBody(string database, string snapshot, IReadOnlyList<UpdateDatabaseEntry> changes) 
        {
            this.database = database;
            this.snapshot = snapshot;
            this.changes = changes;
        }
    }

    internal sealed class KeyPathValue
    {
        public bool Exists { get; }

        public object? Value { get; } = null;

        public KeyPathValue()
        {
            Exists = false;
        }

        public KeyPathValue(object? value)
        {
            Exists = true;
            Value = value;
        }
    }

    internal readonly struct CompareResult
    {
        public bool Success { get; init; } = true;

        public string KeyPath { get; init; } = "";

        public KeyPathValue Expected { get; init; } = new KeyPathValue();

        public KeyPathValue Actual { get; init; } = new KeyPathValue();

        public CompareResult()
        {

        }
    }

    internal static CompareResult IsEqual(Database db, string keyPath, Blob expected, object? actual)
    {
        var _ = expected.Content; // HACK: Force load the properties of the blob
        if (actual is not Blob otherBlob || otherBlob.Content == null) {
            return new CompareResult
            {
                Success = false,
                KeyPath = keyPath,
                Expected = new KeyPathValue(expected.ToDocumentObject()),
                Actual = new KeyPathValue(actual?.ToDocumentObject())
            };
        }

        var blobsEqual = expected.Equals(actual);
        if (!blobsEqual) {
            return new CompareResult
            {
                Success = false,
                KeyPath = keyPath,
                Expected = new KeyPathValue(expected.ToDocumentObject()),
                Actual = new KeyPathValue(actual?.ToDocumentObject())
            };
        }

        return new CompareResult { Success = true };
    }

    internal static CompareResult IsEqual(Database db, string keyPath, object? expected, object? actual)
    {
        switch(expected) {
            case null:
                return new CompareResult
                {
                    Success = actual == null,
                    KeyPath = keyPath,
                    Expected = new KeyPathValue(expected.ToDocumentObject()),
                    Actual = new KeyPathValue(actual?.ToDocumentObject())
                };
            case Blob blob:
                return IsEqual(db, keyPath, blob, actual);
            case IMutableArray arr:
                return IsEqual(db, keyPath, arr, actual as IArray);
            case IMutableDictionary dict:
                return IsEqual(db, keyPath, dict, actual as IDictionaryObject);
            default:
                return new CompareResult
                {
                    Success = expected.Equals(actual),
                    KeyPath = keyPath,
                    Expected = new KeyPathValue(expected.ToDocumentObject()),
                    Actual = new KeyPathValue(actual?.ToDocumentObject())
                };
        }
    }

    internal static CompareResult IsEqual(Database db, string keyPath, IMutableArray expected, IArray? actual)
    {
        if(actual == null || expected.Count != actual.Count) {
            return new CompareResult
            {
                Success = false,
                KeyPath = keyPath,
                Expected = new KeyPathValue(expected.ToList()),
                Actual = new KeyPathValue(actual?.ToList())
            };
        }

        for(int i = 0; i < expected.Count; i++) {
            var leftVal = expected.GetValue(i);
            var rightVal = actual.GetValue(i);
            var result = IsEqual(db, keyPath + $"[{i}]", leftVal.ToDocumentObject(), rightVal.ToDocumentObject());
            if(!result.Success) {
                return result;
            }
        }

        return new CompareResult();
    }

    internal static CompareResult IsEqual(Database db, string keyPath, IMutableDictionary expected, IDictionaryObject? actual)
    {
        if(actual == null) {
            return new CompareResult
            {
                Success = false,
                KeyPath = keyPath,
                Expected = new KeyPathValue(expected.ToDictionary()),
                Actual = new KeyPathValue(new KeyPathValue(null))
            };
        }

        foreach(var key in expected.Keys) {
            if(!actual.Contains(key)) {
                return new CompareResult
                {
                    Success = false,
                    KeyPath = keyPath + $".{key}",
                    Expected = new KeyPathValue(expected.GetValue(key).ToDocumentObject()),
                    Actual = new KeyPathValue()
                };
            }

            var leftVal = expected.GetValue(key);
            var rightVal = actual.GetValue(key);
            var result = IsEqual(db, keyPath + $".{key}", leftVal, rightVal);
            if (!result.Success) {
                return result;
            }
        }

        foreach(var key in actual.Keys) {
            if(!expected.Contains(key)) {
                return new CompareResult
                {
                    Success = false,
                    KeyPath = keyPath + $".{key}",
                    Expected = new KeyPathValue(),
                    Actual = new KeyPathValue(actual.GetValue(key).ToDocumentObject())
                };
            }
        }

        return new CompareResult();
    }

    public static void HandleCompareFailure(Document existing, CompareResult compareResult, HttpListenerResponse response, int version)
    {
        dynamic responseBody = new ExpandoObject();
        responseBody.result = false;
        responseBody.description = $"Document '{existing.Id}' in '{existing.Collection!.Scope.Name}.{existing.Collection!.Name}' had unexpected properties at key '{compareResult.KeyPath.Substring(2)}'";
        if (compareResult.Actual.Exists) {
            responseBody.actual = compareResult.Actual.Value;
            if(compareResult.Actual.Value is Blob b && b.Content == null) {
                responseBody.actual = "Blob data missing from DB";
            }
        }

        if (compareResult.Expected.Exists) {
            responseBody.expected = compareResult.Expected.Value;
        }

        responseBody.document = existing.ToDictionary();

        try {
            response.WriteBody((object)responseBody, version);
        } catch(Exception ex) {
            Console.WriteLine(ex);
        }
    }

    [HttpHandler("verifyDocuments")]
    public static async Task VerifyDocumentsHandler(int version, JsonDocument body, HttpListenerResponse response)
    {
        if (!body.RootElement.TryDeserialize<VerifyDocumentsBody>(response, version, out var verifyBody)) {
            return;
        }

        var db = CBLTestServer.Manager.GetDatabase(verifyBody.database);
        if (db == null) {
            // Error 1 : The specified database was not found.
            response.WriteBody(Router.CreateErrorResponse($"Unable to find db named '{verifyBody.database}'!"), version, HttpStatusCode.BadRequest);
            return;
        }

        var snapshot = CBLTestServer.Manager.GetObject<Snapshot>(verifyBody.snapshot);
        if(snapshot == null) {
            // Error 2 : The specified snapshot was not found.
            response.WriteBody(Router.CreateErrorResponse($"Unable to find snapshot named '{verifyBody.snapshot}'!"), version, HttpStatusCode.BadRequest);
            return;
        }

        var seenKeys = new HashSet<string>();
        foreach(var change in verifyBody.changes) {
            var collSpec = CollectionSpec(change.collection);
            var key = $"{collSpec.scope}.{collSpec.name}.{change.documentID}";
            seenKeys.Add(key);
            if(!snapshot.ContainsKey(key)) {
                // Error 3 : The document in the collection didn't exist in the snapshot.
                response.WriteBody(Router.CreateErrorResponse($"Document '{change.documentID}' in '{change.collection}' does not exist in the snapshot"), version, HttpStatusCode.BadRequest);
                return;
            }

            using var existing = db.GetCollection(collSpec.name, collSpec.scope)?.GetDocument(change.documentID);
            if (change.Type == UpdateDatabaseType.Purge || change.Type == UpdateDatabaseType.Delete) {
                if(existing != null) {
                    // Case 2 : Document should be deleted but it wasn't.
                    // Case 3 : Document should be purged but it wasn't.
                    var verb = change.Type == UpdateDatabaseType.Purge ? "purged" : "deleted";
                    response.WriteBody(new { 
                        result = false, 
                        description = $"Document '{change.documentID}' in '{change.collection}' was not {verb}" 
                    }, version);
                    return;
                }

                continue;
            }

            if (existing == null) {
                // Case 1: Document should exist in the collection but it doesn't exist to verify.
                response.WriteBody(new { 
                    result = false,
                    description = $"Document '{change.documentID}' in '{change.collection}' was not found" 
                }, version);
                return;
            }

            var snapshotDoc = snapshot[key];
            var mutableCopy = snapshotDoc?.ToMutable() ?? new MutableDocument(change.documentID);
            if (change.updatedProperties != null) {
                foreach (var update in change.updatedProperties) {
                    foreach (var entry in update) {
                        KeyPathParser.Update(mutableCopy, entry.Key, entry.Value);
                    }
                }
            }

            if(change.removedProperties != null) {
                foreach(var removed in change.removedProperties) {
                    KeyPathParser.Remove(mutableCopy, removed);
                }
            }

            if(change.updatedBlobs != null) {
                foreach(var entry in change.updatedBlobs) {
                    var blob = await CBLTestServer.Manager.LoadBlob(entry.Value).ConfigureAwait(false);
                    KeyPathParser.Update(mutableCopy, entry.Key, new Blob("image/jpeg", blob));
                }
            }

            var compareResult = IsEqual(db, "$", mutableCopy, existing);
            if(!compareResult.Success) {
                // Case 4 : Document has unexpected properties.
                HandleCompareFailure(existing, compareResult, response, version);
                return;
            }
        }

        foreach (var entry in snapshot) {
            if (seenKeys.Contains(entry.Key)) {
                // Already validated in the previous logic
                continue;
            }

            // If we made it this far, this is an unmodified entry in the snapshot
            var components = entry.Key.Split('.');
            if (components.Length != 3) {
                throw new ApplicationException($"Invalid key in snapshot {entry.Key}");
            }

            var collection = String.Join('.', components.Take(2));

            using var existing = db.GetCollection(components[0], components[1])?.GetDocument(components[2]);
            if(entry.Value == null && existing != null) {
                // Case 5 : Document shouldn't exist (null value in the snapshot), but the document does exist.
                response.WriteBody(new
                {
                    result = false,
                    description = $"Document '{components[2]}' in '{collection}' should not exist"
                }, version);
            }

            if(existing == null) {
                // Case 1: Document should exist in the collection but it doesn't exist to verify.
                response.WriteBody(new
                {
                    result = false,
                    description = $"Document '{components[2]}' in '{collection}' was not found"
                }, version);
                return;
            }

            var compareResult = IsEqual(db, "$", entry.Value, existing);
            if (!compareResult.Success) {
                // Case 4 : Document has unexpected properties.
                HandleCompareFailure(existing, compareResult, response, version);
                return;
            }
        }

        response.WriteBody(new { result = true }, version);
    }
}
