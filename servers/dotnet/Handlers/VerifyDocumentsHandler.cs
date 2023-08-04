using Couchbase.Lite;
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

    internal static (bool success, object? expected, object? actual) IsEqual(object? left, object? right)
    {
        switch(left) {
            case null:
                return (right == null, null, null);
            case IArray arr:
                return IsEqual(arr, right as IMutableArray);
            case IDictionaryObject dict:
                return IsEqual(dict, right as IMutableDictionary);
            default:
                return (left.Equals(right), null, null);
        }
    }

    internal static (bool success, object? expected, object? actual) IsEqual(IArray left, IMutableArray? right)
    {
        if(right == null) {
            return (false, left, right);
        }

        if (left.Count != right.Count) {
            return (false, left, right);
        }

        for(int i = 0; i < left.Count; i++) {
            var leftVal = left.GetValue(i);
            var rightVal = right.GetValue(i);
            var result = IsEqual(leftVal, rightVal);
            if(!result.success) {
                return result;
            }
        }

        return (true, null, null);
    }

    internal static (bool success, object? expected, object? actual) IsEqual(IDictionaryObject left, IMutableDictionary? right)
    {
        if(right == null) {
            return (false, left, right);
        }

        if(left.Count != right.Count) {
            return (false, left, right);
        }

        foreach(var key in left.Keys) {
            if(!right.Contains(key)) {
                return (false, left, right);
            }

            var leftVal = left.GetValue(key);
            var rightVal = right.GetValue(key);
            var result = IsEqual(leftVal, rightVal);
            if (!result.success) {
                if(result.actual == null) {
                    var tmpRight = right.ToDictionary();
                    var tmpLeft = left.ToDictionary();
                    foreach(var k in tmpLeft.Keys) {
                        if(k != key) {
                            tmpLeft.Remove(k);
                        }    
                    }

                    foreach(var k in tmpRight.Keys) {
                        if(k != key) {
                            tmpRight.Remove(k);
                        }
                    }

                    result.actual = tmpRight;
                    result.expected = tmpLeft;
                }

                return result;
            }
        }

        return (true, null, null);
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
                response.WriteBody(Router.CreateErrorResponse($"{key} does not exist in the snapshot"), version, HttpStatusCode.BadRequest);
                return;
            }

            using var existing = db.GetCollection(collSpec.name, collSpec.scope)?.GetDocument(change.documentID);
            if (change.Type == UpdateDatabaseType.Purge || change.Type == UpdateDatabaseType.Delete) {
                
                if(existing != null) {
                    response.WriteBody(new { 
                        result = false, 
                        description = $"Deleted or purged document {key} still exists!" 
                    }, version);
                    return;
                }

                continue;
            }

            if (existing == null) {
                response.WriteBody(new { 
                    result = false,
                    description = $"Document {key} not found to verify!" 
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

            var compareResult = IsEqual(existing, mutableCopy);
            if(!compareResult.success) {
                response.WriteBody(new
                {
                    result = false,
                    description = $"Contents for document {key} did not match!",
                    expected = compareResult.expected!,
                    actual = compareResult.actual!
                }, version);
                return;
            }
        }

        response.WriteBody(new { result = true }, version);
    }
}
