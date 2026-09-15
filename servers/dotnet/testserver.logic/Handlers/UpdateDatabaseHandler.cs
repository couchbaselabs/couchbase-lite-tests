using System.Diagnostics.CodeAnalysis;
using Couchbase.Lite;
using System.Net;
using System.Text.Json;
using System.Text.Json.Serialization;
using JetBrains.Annotations;
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

    [SuppressMessage("ReSharper", "InconsistentNaming")]
    [method: JsonConstructor]
    internal readonly record struct UpdateDatabaseEntry(
        string type,
        string collection,
        string documentID,
        [property: UsedImplicitly] IReadOnlyList<IReadOnlyDictionary<string, object>>? updatedProperties = null,
        [property: UsedImplicitly] IReadOnlyList<string>? removedProperties = null,
        [property: UsedImplicitly] IReadOnlyDictionary<string, string>? updatedBlobs = null)
    {
        [JsonIgnore]
        public UpdateDatabaseType Type { get; } = type.ToUpperInvariant() switch
        {
            "UPDATE" => UpdateDatabaseType.Update,
            "DELETE" => UpdateDatabaseType.Delete,
            "PURGE" => UpdateDatabaseType.Purge,
            _ => throw new JsonException($"Invalid 'type' in database update: {type}")
        };

        [UsedImplicitly]
        public required string type { get; init; } = type;

        public required string collection { get; init; } = collection;

        public required string documentID { get; init; } = documentID;
    }

    [SuppressMessage("ReSharper", "InconsistentNaming")]
    [method: JsonConstructor]
    internal readonly record struct UpdateDatabaseBody(string database, IReadOnlyList<UpdateDatabaseEntry> updates)
    {
        public required string database { get; init; } = database;

        public required IReadOnlyList<UpdateDatabaseEntry> updates { get; init; } = updates;
    }

    private static readonly IReadOnlyDictionary<string, string> BlobTypeMap = new Dictionary<string, string>
    {
        ["jpg"] = "image/jpeg"
    };

    private static string BlobType(string filename) =>
        BlobTypeMap.GetValueOrDefault(filename.Split(".").Last(), "application/octet-stream");

    private static Collection GetCollection(Database db, string name)
    {
        var collSpec = CollectionSpec(name);
        return collSpec.name == "_default" 
            ? db.GetCollection(collSpec.name, collSpec.scope)! 
            : db.CreateCollection(collSpec.name, collSpec.scope);
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
    public static async Task UpdateDatabaseHandler(Session session, JsonDocument body, HttpListenerResponse response)
    {
        if(!body.RootElement.TryDeserialize<UpdateDatabaseBody>(out var updateBody, out var ex)) {
            await response.WriteDeserializationError(ex).ConfigureAwait(false);
            return;
        }

        var db = session.ObjectManager.GetDatabase(updateBody.database);
        if(db == null) {
            await response.WriteBody(Router.CreateErrorResponse($"Unable to find database named '{updateBody.database}'"), HttpStatusCode.BadRequest).ConfigureAwait(false);
            return;
        }

        // This has to be done here because it is async and can't go inside inBatch()
        var blobUpdate = new Dictionary<string, object>();
        foreach(var update in updateBody.updates.Where(x => x.updatedBlobs != null && x.updatedBlobs.Any())) {
            foreach(var b in update.updatedBlobs!) {
                var deduplicatedKey = $"{update.collection}/{update.documentID}/{b.Key}";
                var nextBlob = await session.ObjectManager.LoadBlob(b.Value).ConfigureAwait(false);
                blobUpdate[deduplicatedKey] = new Blob(BlobType(b.Value), nextBlob);
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
                            if (entry.removedProperties != null) {
                                RemoveDictionaryProperties(doc, entry.removedProperties);
                            }

                            if (entry.updatedProperties != null) {
                                UpdateDictionaryProperties(doc, entry.updatedProperties);
                            }

                            if (entry.updatedBlobs != null) {
                                UpdateDictionaryProperties(doc, entry.updatedBlobs
                                        .Select(x => new Dictionary<string, object> {
                                            [x.Key] = blobUpdate[$"{entry.collection}/{entry.documentID}/{x.Key}"] })
                                        .ToList());
                            }

                            collection.Save(doc);
                            break;
                        }
                    }
                }
            });
        } catch(KeyPathException e) {
            await response.WriteBody(new ErrorReturnBody
            {
                domain = TestServerErrorDomain.TestServer,
                code = 1,
                message = e.Message
            }, HttpStatusCode.BadRequest).ConfigureAwait(false);
        } finally
        {
            foreach (var cs in blobUpdate.Values.Select(blob => ((Blob)blob).ContentStream).OfType<Stream>())
            {
                await cs.DisposeAsync().ConfigureAwait(false);
            }
        }

        await response.WriteEmptyBody().ConfigureAwait(false);
    }
}
