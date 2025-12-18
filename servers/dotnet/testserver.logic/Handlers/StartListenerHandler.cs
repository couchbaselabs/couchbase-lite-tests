using Couchbase.Lite;
using Couchbase.Lite.P2P;
using System.Net;
using System.Text.Json;
using TestServer.Utilities;

namespace TestServer.Handlers;


internal static partial class HandlerList
{
    internal readonly record struct ReplicatorIdentityBody
    {
        public required string encoding { get; init; }

        public required string data { get; init; }

        public required string password { get; init; }
    }
    internal readonly record struct StartListenerBody
    {
        public required string database { get; init; }

        public required string[] collections { get; init; }

        public ushort port { get; init; }

        public bool disableTLS { get; init; } = false;

        public ReplicatorIdentityBody? identity { get; init; }

    }

    [HttpHandler("startListener")]
    public static Task StartListenerHandler(int version, Session session, JsonDocument body, HttpListenerResponse response)
    {
        if (!body.RootElement.TryDeserialize<StartListenerBody>(response, version, out var deserializedBody)) {
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
        if (!deserializedBody.disableTLS)
        {
            var identityBody = deserializedBody.identity.Value;
            var label = $"dotnet-p2p-{deserializedBody.database}";
            var existing = TlsIdentity.GetIdentity(label);
            if (existing != null)
            {
                listenerConfig.TlsIdentity = existing;
            }
            else
            {
                byte[] p12bytes;
                try {
                    p12bytes = Convert.FromBase64String(identityBody.data);
                }
                catch {
                    response.WriteBody(new {
                        domain = "TESTSERVER",
                        code = 400,
                        message = "Invalid base64 identity data."
                    }, version, HttpStatusCode.BadRequest);
                    return Task.CompletedTask;
                }
                TlsIdentity.DeleteIdentity(label);
                TlsIdentity imported;
                try
                {
                    imported = TlsIdentity.ImportIdentity(p12bytes, identityBody.password, label);
                }
                catch (Exception e)
                {
                    response.WriteBody(new {
                        domain = "TESTSERVER",
                        code = 400,
                        message = $"Failed to import TLS identity: {e.Message}"
                    }, version, HttpStatusCode.BadRequest);
                    return Task.CompletedTask;
                }

                listenerConfig.TlsIdentity = imported;
            }
        }
        (var listener, var id) = session.ObjectManager.RegisterObject(() => new URLEndpointListener(listenerConfig));
        listener.Start();

        var responseBody = new Dictionary<string, object>
        {
            { "id", id },
            { "port", listener.Port }
        };

        response.WriteBody(responseBody, version);
        return Task.CompletedTask;
    }
}
