using Couchbase.Lite;
using Couchbase.Lite.P2P;
using System.Net;
using System.Text.Json;
using TestServer.Utilities;

namespace TestServer.Handlers;


internal static partial class HandlerList
{
    internal readonly record struct StartListenerBody
    {
        public required string database { get; init; }

        public required string[] collections { get; init; }

        public ushort port { get; init; }

        public bool disableTLS { get; init; }
    }

    [HttpHandler("startListener")]
    public static Task StartListenerHandler(Session session, JsonDocument body, HttpListenerResponse response)
    {
        if (!body.RootElement.TryDeserialize<StartListenerBody>(response, out var deserializedBody)) {
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

            response.WriteBody(errorObject, HttpStatusCode.BadRequest);
            return Task.CompletedTask;
        }

        var collectionObjects = new List<Collection>();
        foreach(var c in deserializedBody.collections) {
            var collSpec = CollectionSpec(c);
            var collection = dbObject.GetCollection(collSpec.name, collSpec.scope)
                ?? throw new JsonException($"Collection {c} does not exist in db!");
            collectionObjects.Add(collection);
        }

        var listenerConfig = new URLEndpointListenerConfiguration(collectionObjects)
        {
            Port = deserializedBody.port,
            DisableTLS = deserializedBody.disableTLS
        };
        (var listener, var id) = session.ObjectManager.RegisterObject(() => new URLEndpointListener(listenerConfig));
        listener.Start();

        var responseBody = new Dictionary<string, object>
        {
            { "id", id },
            { "port", listener.Port }
        };

        response.WriteBody(responseBody);
        return Task.CompletedTask;
    }
}
