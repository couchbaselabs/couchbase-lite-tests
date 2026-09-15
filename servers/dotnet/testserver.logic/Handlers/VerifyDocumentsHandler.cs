using System.Diagnostics.CodeAnalysis;
using Couchbase.Lite;
using System.Dynamic;
using System.Net;
using System.Text.Json;
using System.Text.Json.Serialization;
using TestServer.Utilities;

namespace TestServer.Handlers;

internal static partial class HandlerList
{
    [SuppressMessage("ReSharper", "InconsistentNaming")]
    [method: JsonConstructor]
    internal readonly record struct VerifyDocumentsBody(
        string database,
        string snapshot,
        IReadOnlyList<UpdateDatabaseEntry> changes)
    {
        public required string database { get; init; } = database;

        public required string snapshot { get; init; } = snapshot;

        public required IReadOnlyList<UpdateDatabaseEntry> changes { get; init; } = changes;
    }

    internal sealed class KeyPathValue
    {
        public bool Exists { get; }

        public object? Value { get; }

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
                Actual = new KeyPathValue(actual.ToDocumentObject())
            };
        }

        return new CompareResult { Success = true };
    }

    internal static CompareResult IsEqual(Database db, string keyPath, object? expected, object? actual)
    {
        return expected switch
        {
            null => new CompareResult
            {
                Success = actual == null,
                KeyPath = keyPath,
                Expected = new KeyPathValue(expected.ToDocumentObject()),
                Actual = new KeyPathValue(actual?.ToDocumentObject())
            },
            Blob blob => IsEqual(db, keyPath, blob, actual),
            IMutableArray arr => IsEqual(db, keyPath, arr, actual as IArray),
            IMutableDictionary dict => IsEqual(db, keyPath, dict, actual as IDictionaryObject),
            _ => new CompareResult
            {
                Success = expected.Equals(actual),
                KeyPath = keyPath,
                Expected = new KeyPathValue(expected.ToDocumentObject()),
                Actual = new KeyPathValue(actual?.ToDocumentObject())
            }
        };
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

    public static async Task HandleCompareFailure(Document existing, CompareResult compareResult, HttpListenerResponse response)
    {
        dynamic responseBody = new ExpandoObject();
        responseBody.result = false;
        responseBody.description = $"Document '{existing.Id}' in '{existing.Collection!.Scope.Name}.{existing.Collection!.Name}' had unexpected properties at key '{compareResult.KeyPath[2..]}'";
        if (compareResult.Actual.Exists) {
            responseBody.actual = compareResult.Actual.Value;
            if(compareResult.Actual.Value is Blob { Content: null }) {
                responseBody.description = $"Document '{existing.Id}' in '{existing.Collection!.Scope.Name}.{existing.Collection!.Name}' had non-existent blob at key '{compareResult.KeyPath[2..]}'";
            }
        }

        if (compareResult.Expected.Exists) {
            responseBody.expected = compareResult.Expected.Value;
        }

        responseBody.document = existing.ToDictionary();

        try {
            await response.WriteBody((object)responseBody).ConfigureAwait(false);
        } catch(Exception ex) {
            Serilog.Log.Logger.Error(ex, "Error writing VerifyDocuments body to response");
        }
    }

    [HttpHandler("verifyDocuments")]
    public static async Task VerifyDocumentsHandler(Session session, JsonDocument body, HttpListenerResponse response)
    {
        if (!body.RootElement.TryDeserialize<VerifyDocumentsBody>(out var verifyBody, out var ex)) {
            await response.WriteDeserializationError(ex).ConfigureAwait(false);
            return;
        }

        var db = session.ObjectManager.GetDatabase(verifyBody.database);
        if (db == null) {
            // Error 1 : The specified database was not found.
            await response.WriteBody(Router.CreateErrorResponse($"Unable to find db named '{verifyBody.database}'!"), HttpStatusCode.BadRequest).ConfigureAwait(false);
            return;
        }

        var snapshot = session.ObjectManager.GetObject<Snapshot>(verifyBody.snapshot);
        if(snapshot == null) {
            // Error 2 : The specified snapshot was not found.
            await response.WriteBody(Router.CreateErrorResponse($"Unable to find snapshot named '{verifyBody.snapshot}'!"), HttpStatusCode.BadRequest).ConfigureAwait(false);
            return;
        }

        var seenKeys = new HashSet<string>();
        foreach(var change in verifyBody.changes) {
            var collSpec = CollectionSpec(change.collection);
            var key = $"{collSpec.scope}.{collSpec.name}.{change.documentID}";
            seenKeys.Add(key);
            if(!snapshot.ContainsKey(key)) {
                // Error 3 : The document in the collection didn't exist in the snapshot.
                await response.WriteBody(Router.CreateErrorResponse($"Document '{change.documentID}' in '{change.collection}' does not exist in the snapshot"), HttpStatusCode.BadRequest).ConfigureAwait(false);
                return;
            }

            using var existing = db.GetCollection(collSpec.name, collSpec.scope)?.GetDocument(change.documentID);
            if (change.Type is UpdateDatabaseType.Purge or UpdateDatabaseType.Delete) {
                if(existing != null) {
                    // Case 2 : Document should be deleted, but it wasn't.
                    // Case 3 : Document should be purged, but it wasn't.
                    var verb = change.Type == UpdateDatabaseType.Purge ? "purged" : "deleted";
                    await response.WriteBody(new {
                        result = false,
                        description = $"Document '{change.documentID}' in '{change.collection}' was not {verb}"
                    }).ConfigureAwait(false);
                    return;
                }

                continue;
            }

            if (existing == null) {
                // Case 1: Document should exist in the collection, but it doesn't exist to verify.
                await response.WriteBody(new {
                    result = false,
                    description = $"Document '{change.documentID}' in '{change.collection}' was not found"
                }).ConfigureAwait(false);
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
                    var blob = await session.ObjectManager.LoadBlob(entry.Value).ConfigureAwait(false);
                    KeyPathParser.Update(mutableCopy, entry.Key, new Blob(BlobType(entry.Value), blob));
                }
            }

            var compareResult = IsEqual(db, "$", mutableCopy, existing);
            if(!compareResult.Success) {
                // Case 4 : Document has unexpected properties.
                await HandleCompareFailure(existing, compareResult, response).ConfigureAwait(false);
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

            using var existing = db.GetCollection(components[1], components[0])?.GetDocument(components[2]);
            if (entry.Value == null && existing != null) {
                // Case 5 : Document shouldn't exist (null value in the snapshot), but the document does exist.
                await response.WriteBody(new
                {
                    result = false,
                    description = $"Document '{components[2]}' in '{collection}' should not exist"
                }).ConfigureAwait(false);
            } else if (entry.Value != null && existing == null) {
                // Case 1: Document should exist in the collection, but it doesn't exist to verify.
                await response.WriteBody(new
                {
                    result = false,
                    description = $"Document '{components[2]}' in '{collection}' was not found"
                }).ConfigureAwait(false);

                return;
            } else if (existing != null) {
                var compareResult = IsEqual(db, "$", entry.Value, existing);
                if (!compareResult.Success) {
                    // Case 4 : Document has unexpected properties.
                    await HandleCompareFailure(existing, compareResult, response).ConfigureAwait(false);
                    return;
                }
            }
        }

        await response.WriteBody(new { result = true }).ConfigureAwait(false);
    }
}
