using Couchbase.Lite;
using System;
using System.Collections.Generic;
using System.Collections.Specialized;
using System.Linq;
using System.Net;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Threading.Tasks;
using TestServer.Utilities;

namespace TestServer.Handlers;

internal static partial class HandlerList
{
    internal enum UpdateDatabaseType
    {
        Update,
        Delete,
        Purge
    }

    internal readonly record struct UpdateDatabaseEntry
    {
        [JsonIgnore]
        public UpdateDatabaseType Type { get; }

        public required string type { get; init; }

        public required string collection { get; init; }

        public required string documentID { get; init; }

        public IReadOnlyList<IReadOnlyDictionary<string, object>>? updatedProperties { get; init; }

        public IReadOnlyList<string>? removedProperties { get; init; }

        public IReadOnlyDictionary<string, string>? updatedBlobs { get; init; }

        [JsonConstructor]
        public UpdateDatabaseEntry(string type, string collection, string documentID,
            IReadOnlyList<IReadOnlyDictionary<string, object>>? updatedProperties = null,
            IReadOnlyList<string>? removedProperties = null, IReadOnlyDictionary<string, string>? updatedBlobs = null)
        {
            if(type.ToUpperInvariant() == "UPDATE") {
                Type = UpdateDatabaseType.Update;
            } else if(type.ToUpperInvariant() == "DELETE") {
                Type = UpdateDatabaseType.Delete;
            } else if(type.ToUpperInvariant() == "PURGE") {
                Type = UpdateDatabaseType.Purge;
            } else {
                throw new JsonException($"Invalid 'type' in database update: {type}");
            }

            this.type = type;
            this.documentID = documentID;
            this.collection = collection;
            this.updatedProperties = updatedProperties;
            this.removedProperties = removedProperties;
            this.updatedBlobs = updatedBlobs;
        }
    }

    internal readonly record struct UpdateDatabaseBody
    {
        public required string database { get; init; }

        public required IReadOnlyList<UpdateDatabaseEntry> updates { get; init; }

        [JsonConstructor]
        public UpdateDatabaseBody(string database, IReadOnlyList<UpdateDatabaseEntry> updates)
        {
            this.database = database;
            this.updates = updates;
        }
    }

    private static Collection GetCollection(Database db, string name)
    {
        var collSpec = CollectionSpec(name);
        if(collSpec.name == "_default") {
            return db.GetCollection(collSpec.name, collSpec.scope)!;
        }

        return db.CreateCollection(collSpec.name, collSpec.scope);
    }

    private static void UpdateDictionaryProperties(IMutableDictionary dict, IReadOnlyList<IReadOnlyDictionary<string, object>> updates)
    {
        foreach (var update in updates) {
            foreach(var prop in update) {
                KeyPathParser.Update(dict, prop.Key.TrimStart('.', '$'), prop.Value);
            }
        }
    }

    private static void RemoveDictionaryProperties(IMutableDictionary dict, IReadOnlyList<string> props)
    {
        foreach(var prop in props) {
            KeyPathParser.Remove(dict, prop.TrimStart('.', '$'));
        }
    }

    [HttpHandler("updateDatabase")]
    public static async Task UpdateDatabaseHandler(int version, JsonDocument body, HttpListenerResponse response)
    {
        if(!body.RootElement.TryDeserialize<UpdateDatabaseBody>(response, version, out var updateBody)) {
            return;
        }

        var db = CBLTestServer.Manager.GetDatabase(updateBody.database);
        if(db == null) {
            response.WriteBody(Router.CreateErrorResponse($"Unable to find database named '{updateBody.database}'"), version, HttpStatusCode.BadRequest);
            return;
        }

        var blobUpdate = new Dictionary<string, object>();
        foreach(var update in updateBody.updates.Where(x => x.updatedBlobs != null && x.updatedBlobs.Any())) {
            foreach(var b in update.updatedBlobs!) {
                var nextBlob = await CBLTestServer.Manager.LoadBlob(b.Value).ConfigureAwait(false);
                blobUpdate[b.Key] = new Blob("image/jpeg", nextBlob);
            }
        }

        try {
            db.InBatch(() =>
            {
                foreach (var entry in updateBody.updates) {
                    using var collection = GetCollection(db, entry.collection);
                    switch (entry.Type) {
                        case UpdateDatabaseType.Delete: {
                            using var doc = collection.GetDocument(entry.documentID);
                            if (doc != null) {
                                collection.Delete(doc);
                            }

                            break;
                        }
                        case UpdateDatabaseType.Purge: {
                            using var doc = collection.GetDocument(entry.documentID);
                            if (doc != null) {
                                collection.Purge(doc);
                            }

                            break;
                        }
                        case UpdateDatabaseType.Update: {
                            using var doc = collection.GetDocument(entry.documentID)?.ToMutable() ?? new MutableDocument(entry.documentID);
                            if (entry.updatedProperties != null) {
                                UpdateDictionaryProperties(doc, entry.updatedProperties);
                            }

                            if (entry.removedProperties != null) {
                                RemoveDictionaryProperties(doc, entry.removedProperties);
                            }

                            if (blobUpdate.Any()) {
                                UpdateDictionaryProperties(doc, new List<IReadOnlyDictionary<string, object>> { blobUpdate });
                            }

                            collection.Save(doc);
                            break;
                        }
                    }
                }
            });
        } catch(KeyPathException e) {
            response.WriteBody(new ErrorReturnBody
            {
                domain = TestServerErrorDomain.TestServer,
                code = 1,
                message = e.Message
            }, version, HttpStatusCode.BadRequest);
        } finally {
            foreach(var blob in blobUpdate.Values) {
                ((Blob)blob).ContentStream?.Dispose();
            }
        }

        response.WriteEmptyBody(version);
    }
}
