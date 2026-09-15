using System.Diagnostics.CodeAnalysis;
using Couchbase.Lite;
using System.Net;
using System.Text.Json;
using System.Text.Json.Serialization;
using TestServer.Utilities;

namespace TestServer.Handlers;

internal static partial class HandlerList
{
    internal sealed class Snapshot : Dictionary<string, Document?>, IDisposable
    {
        public void Dispose()
        {
            foreach(var doc in Values.NotNull()) {
                doc.Dispose();
            }

            Clear();
        }
    }

    [method: JsonConstructor]
    [SuppressMessage("ReSharper", "InconsistentNaming")]
    internal readonly record struct DocumentEntry(string collection, string id)
    {
        public required string collection { get; init; } = collection;

        public required string id { get; init; } = id;
    }

    [SuppressMessage("ReSharper", "InconsistentNaming")]
    [method: JsonConstructor]
    internal readonly record struct SnapshotDocumentBody(string database, IReadOnlyList<DocumentEntry> documents)
    {
        public required string database { get; init; } = database;

        public required IReadOnlyList<DocumentEntry> documents { get; init; } = documents;
    }

    [HttpHandler("snapshotDocuments")]
    public static async Task SnapshotDocumentsHandler(Session session, JsonDocument body, HttpListenerResponse response)
    {
        if (!body.RootElement.TryDeserialize<SnapshotDocumentBody>(out var snapshotBody, out var ex)) {
            await response.WriteDeserializationError(ex).ConfigureAwait(false);
            return;
        }

        var db = session.ObjectManager.GetDatabase(snapshotBody.database);
        if (db == null) {
            await response.WriteBody(Router.CreateErrorResponse($"Unable to find db named '{snapshotBody.database}'!"), HttpStatusCode.BadRequest).ConfigureAwait(false);
            return;
        }

        var (snapshot, id) = session.ObjectManager.RegisterObject(() => new Snapshot());
        foreach(var snapshotEntry in snapshotBody.documents) {
            var collSpec = CollectionSpec(snapshotEntry.collection);
            var doc = db.GetCollection(collSpec.name, collSpec.scope)?.GetDocument(snapshotEntry.id);
            snapshot[$"{collSpec.scope}.{collSpec.name}.{snapshotEntry.id}"] = doc;
        }

        await response.WriteBody(new { id }).ConfigureAwait(false);
    }
}
