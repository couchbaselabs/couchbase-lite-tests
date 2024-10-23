using Couchbase.Lite;
using Couchbase.Lite.Unsupported;
using System.Net;
using System.Text.Json;
using TestServer.Utilities;

namespace TestServer.Handlers;


internal static partial class HandlerList
{
    internal readonly record struct GetDocumentBody
    {
        public required string database { get; init; }

        public required DocumentEntry document { get; init; }
    }

    [HttpHandler("getDocument")]
    public static Task GetDocumentHandler(int version, Session session, JsonDocument body, HttpListenerResponse response)
    {
        if (!body.RootElement.TryDeserialize<GetDocumentBody>(response, version, out var deserializedBody)) {
            return Task.CompletedTask;
        }

        var dbObject = session.ObjectManager.GetDatabase(deserializedBody.database);
        if (dbObject == null) {
            var errorObject = new
            {
                domain = (int)CouchbaseLiteErrorType.CouchbaseLite + 1,
                code = (int)CouchbaseLiteError.NotFound,
                message = $"database '{deserializedBody.database}' not registered!"
            };

            response.WriteBody(errorObject, version, HttpStatusCode.BadRequest);
            return Task.CompletedTask;
        }

        var collSpec = CollectionSpec(deserializedBody.document.collection);
        using var collection = dbObject.GetCollection(collSpec.name, collSpec.scope) 
            ?? throw new JsonException($"Collection {deserializedBody.document.id} does not exist in db!");

        using var doc = collection.GetDocument(deserializedBody.document.id);
        if(doc == null) {
            response.WriteEmptyBody(version, HttpStatusCode.NotFound);
            return Task.CompletedTask;
        }

        var documentBody = doc.ToDictionary();
        documentBody["_id"] = deserializedBody.document.id;
        documentBody["_revs"] = doc.RevisionIDs();

        response.WriteBody(documentBody, version);
        return Task.CompletedTask;
    }
}
