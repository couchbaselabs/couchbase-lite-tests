using System.Diagnostics.CodeAnalysis;
using Couchbase.Lite;
using Couchbase.Lite.Unsupported;
using System.Net;
using System.Text.Json;
using TestServer.Utilities;

namespace TestServer.Handlers;


internal static partial class HandlerList
{
    [SuppressMessage("ReSharper", "InconsistentNaming")]
    internal readonly record struct GetDocumentBody
    {
        public required string database { get; init; }

        public required DocumentEntry document { get; init; }
    }

    [HttpHandler("getDocument")]
    public static async Task GetDocumentHandler(Session session, JsonDocument body, HttpListenerResponse response)
    {
        if (!body.RootElement.TryDeserialize<GetDocumentBody>(out var deserializedBody, out var ex))
        {
            await response.WriteDeserializationError(ex).ConfigureAwait(false);
            return;
        }

        var dbObject = session.ObjectManager.GetDatabase(deserializedBody.database);
        if (dbObject == null) {
            var errorObject = new
            {
                domain = (int)CouchbaseLiteErrorType.CouchbaseLite + 1,
                code = (int)CouchbaseLiteError.NotFound,
                message = $"database '{deserializedBody.database}' not registered!"
            };

            await response.WriteBody(errorObject, HttpStatusCode.BadRequest).ConfigureAwait(false);
            return;
        }

        var collSpec = CollectionSpec(deserializedBody.document.collection);
        using var collection = dbObject.GetCollection(collSpec.name, collSpec.scope)
            ?? throw new JsonException($"Collection {deserializedBody.document.id} does not exist in db!");

        using var doc = collection.GetDocument(deserializedBody.document.id);
        if(doc == null) {
            await response.WriteEmptyBody(HttpStatusCode.NotFound).ConfigureAwait(false);
            return;
        }

        var documentBody = doc.ToDictionary();
        documentBody["_id"] = deserializedBody.document.id;
        documentBody["_revs"] = doc.RevisionIDs();

        await response.WriteBody(documentBody).ConfigureAwait(false);
    }
}
