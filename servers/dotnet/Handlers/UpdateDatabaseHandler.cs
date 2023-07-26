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

        public JsonElement? updatedProperties { get; init; }

        public JsonElement? removedProperties { get; init; }

        [JsonConstructor]
        public UpdateDatabaseEntry(string type, string collection, string documentID, 
            JsonElement? updatedProperties = null,
            JsonElement? removedProperties = null)
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

    private static void UpdateDictionaryProperties(IMutableDictionary dict, JsonElement delta)
    {
        if(delta.ValueKind != JsonValueKind.Object) {
            throw new InvalidOperationException("UpdateDictionaryProperties called with a non-object delta");
        }

        foreach(var deltaEntry in delta.EnumerateObject()) {
            if(deltaEntry.Value.ValueKind == JsonValueKind.Object) {
                var existingDict = dict.GetDictionary(deltaEntry.Name);
                if(existingDict == null) {
                    existingDict = new MutableDictionaryObject();
                    dict.SetDictionary(deltaEntry.Name, existingDict);
                }

                UpdateDictionaryProperties(existingDict, deltaEntry.Value);
            } else {
                dict.SetValue(deltaEntry.Name, deltaEntry.Value.ToDocumentObject());
            }
        }
    }

    private static void RemoveDictionaryProperties(IMutableDictionary dict, JsonElement delta)
    {
        if (delta.ValueKind != JsonValueKind.Object) {
            throw new InvalidOperationException("UpdateDictionaryProperties called with a non-object delta");
        }

        foreach (var deltaEntry in delta.EnumerateObject()) {
            if (deltaEntry.Value.ValueKind == JsonValueKind.Object) {
                var existingDict = dict.GetDictionary(deltaEntry.Name);
                if (existingDict == null) {
                    return;
                }

                RemoveDictionaryProperties(existingDict, deltaEntry.Value);
            } else {
                dict.Remove(deltaEntry.Name);
            }
        }
    }

    [HttpHandler("updateDatabase")]
    public static void UpdateDatabaseHandler(int version, JsonDocument body, HttpListenerResponse response)
    {
        if(!body.RootElement.TryDeserialize<UpdateDatabaseBody>(response, version, out var updateBody)) {
            return;
        }

        var db = CBLTestServer.Manager.GetDatabase(updateBody.database);
        if(db == null) {
            response.WriteBody(Router.CreateErrorResponse($"Unable to find database named '{updateBody.database}'"), version, HttpStatusCode.BadRequest);
            return;
        }

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
                        if(entry.updatedProperties != null) {
                            UpdateDictionaryProperties(doc, entry.updatedProperties.Value);
                        }
                        
                        if(entry.removedProperties != null) {
                            RemoveDictionaryProperties(doc, entry.removedProperties.Value);
                        }

                        collection.Save(doc);
                        break;
                    }
                }
            }
        });

        response.WriteEmptyBody(version);
    }
}
