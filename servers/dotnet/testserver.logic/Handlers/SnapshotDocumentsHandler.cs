using Couchbase.Lite;
using System.Net;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace TestServer.Handlers;

internal static partial class HandlerList
{
    internal sealed class Snapshot : Dictionary<string, Document?>, IDisposable
    {
        private readonly Dictionary<string, Document?> _documents = new();

        public void Dispose()
        {
            foreach(var doc in _documents.Values.NotNull()) {
                doc.Dispose();
            }

            _documents.Clear();
        }
    }

    internal readonly record struct DocumentEntry
    {
        public required string collection { get; init; }

        public required string id { get; init; }

        [JsonConstructor]
        public DocumentEntry(string collection, string id)
        {
            this.collection = collection;
            this.id = id;
        }
    }

    internal readonly record struct SnapshotDocumentBody
    {
        public required string database { get; init; }

        public required IReadOnlyList<DocumentEntry> documents { get; init; }

        [JsonConstructor]
        public SnapshotDocumentBody(string database, IReadOnlyList<DocumentEntry> documents)
        {
            this.database = database;
            this.documents = documents;
        }
    }

    [HttpHandler("snapshotDocuments")]
    public static Task SnapshotDocumentsHandler(int version, JsonDocument body, HttpListenerResponse response)
    {
        if (!body.RootElement.TryDeserialize<SnapshotDocumentBody>(response, version, out var snapshotBody)) {
            return Task.CompletedTask;
        }

        var db = CBLTestServer.Manager.GetDatabase(snapshotBody.database);
        if (db == null) {
            response.WriteBody(Router.CreateErrorResponse($"Unable to find db named '{snapshotBody.database}'!"), version, HttpStatusCode.BadRequest);
            return Task.CompletedTask;
        }

        var (snapshot, id) = CBLTestServer.Manager.RegisterObject(() => new Snapshot());
        foreach(var snapshotEntry in snapshotBody.documents) {
            var collSpec = CollectionSpec(snapshotEntry.collection);
            var doc = db.GetCollection(collSpec.name, collSpec.scope)?.GetDocument(snapshotEntry.id);
            snapshot[$"{collSpec.scope}.{collSpec.name}.{snapshotEntry.id}"] = doc;
        }

        response.WriteBody(new { id }, version);
        return Task.CompletedTask;
    }
}
