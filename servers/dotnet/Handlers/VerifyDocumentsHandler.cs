using Couchbase.Lite;
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

    internal static (bool success, string keyPath, KeyPathValue expected, KeyPathValue actual) IsEqual(string keyPath, object? expected, object? actual)
    {
        switch(expected) {
            case null:
                return (actual == null, keyPath, new KeyPathValue(expected), new KeyPathValue(actual?.ToDocumentObject()));
            case IMutableArray arr:
                return IsEqual(keyPath, arr, actual as IArray);
            case IMutableDictionary dict:
                return IsEqual(keyPath, dict, actual as IDictionaryObject);
            default:
                return (expected.Equals(actual), keyPath, new KeyPathValue(expected.ToDocumentObject()), new KeyPathValue(actual.ToDocumentObject()));
        }
    }

    internal static (bool success, string keyPath, KeyPathValue expected, KeyPathValue actual) IsEqual(string keyPath, IMutableArray expected, IArray? actual)
    {
        if(actual == null) {
            return (false, keyPath, new KeyPathValue(expected.ToList()), new KeyPathValue(actual?.ToList()));
        }

        if (expected.Count != actual.Count) {
            return (false, keyPath, new KeyPathValue(expected.ToList()), new KeyPathValue(actual.ToList()));
        }

        for(int i = 0; i < expected.Count; i++) {
            var leftVal = expected.GetValue(i);
            var rightVal = actual.GetValue(i);
            var result = IsEqual(keyPath + $"[{i}]", leftVal.ToDocumentObject(), rightVal.ToDocumentObject());
            if(!result.success) {
                return result;
            }
        }

        return (true, keyPath, new KeyPathValue(), new KeyPathValue());
    }

    internal static (bool success, string keyPath, KeyPathValue expected, KeyPathValue actual) IsEqual(string keyPath, IMutableDictionary expected, IDictionaryObject? actual)
    {
        if(actual == null) {
            return (false, keyPath, new KeyPathValue(expected.ToDictionary()), new KeyPathValue());
        }

        foreach(var key in expected.Keys) {
            if(!actual.Contains(key)) {
                return (false, keyPath + $".{key}", new KeyPathValue(expected.GetValue(key).ToDocumentObject()), new KeyPathValue());
            }

            var leftVal = expected.GetValue(key);
            var rightVal = actual.GetValue(key);
            var result = IsEqual(keyPath + $".{key}", leftVal, rightVal);
            if (!result.success) {
                return result;
            }
        }

        foreach(var key in actual.Keys) {
            if(!expected.Contains(key)) {
                return (false, keyPath + $".{key}", new KeyPathValue(), new KeyPathValue(actual.GetValue(key).ToDocumentObject()));
            }
        }

        return (true, keyPath, new KeyPathValue(expected), new KeyPathValue(actual));
    }

    [HttpHandler("verifyDocuments")]
    public static void VerifyDocumentsHandler(int version, JsonDocument body, HttpListenerResponse response)
    {
        if (!body.RootElement.TryDeserialize<VerifyDocumentsBody>(response, version, out var verifyBody)) {
            return;
        }

        var db = CBLTestServer.Manager.GetDatabase(verifyBody.database);
        if (db == null) {
            response.WriteBody(Router.CreateErrorResponse($"Unable to find db named '{verifyBody.database}'!"), version, HttpStatusCode.BadRequest);
            return;
        }

        var snapshot = CBLTestServer.Manager.GetObject<Snapshot>(verifyBody.snapshot);
        if(snapshot == null) {
            response.WriteBody(Router.CreateErrorResponse($"Unable to find snapshot named '{verifyBody.snapshot}'!"), version, HttpStatusCode.BadRequest);
            return;
        }

        foreach(var change in verifyBody.changes) {
            var collSpec = CollectionSpec(change.collection);
            var key = $"{collSpec.scope}.{collSpec.name}.{change.documentID}";
            if(!snapshot.ContainsKey(key)) {
                response.WriteBody(Router.CreateErrorResponse($"Document '{change.documentID}' in '{change.collection}' does not exist in the snapshot"), version, HttpStatusCode.BadRequest);
                return;
            }

            using var existing = db.GetCollection(collSpec.name, collSpec.scope)?.GetDocument(change.documentID);
            if (change.Type == UpdateDatabaseType.Purge || change.Type == UpdateDatabaseType.Delete) {
                if(existing != null) {
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
                response.WriteBody(new { 
                    result = false,
                    description = $"Document '{change.documentID} in '{change.collection}' not found" 
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

            var compareResult = IsEqual("$", mutableCopy, existing);
            if(!compareResult.success) {
                dynamic responseBody = new ExpandoObject();
                responseBody.result = false;
                responseBody.description = $"Document '{change.documentID}' in '{change.collection}' had unexpected properties at key '{compareResult.keyPath.Substring(2)}'";
                if(compareResult.actual.Exists) {
                    responseBody.actual = compareResult.actual.Value;
                }

                if(compareResult.expected.Exists) {
                    responseBody.expected = compareResult.expected.Value;
                }

                responseBody.document = existing.ToDictionary();

                response.WriteBody((object)responseBody, version);
                return;
            }
        }

        response.WriteBody(new { result = true }, version);
    }
}
