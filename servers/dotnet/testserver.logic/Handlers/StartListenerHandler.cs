using System.Diagnostics.CodeAnalysis;
using Couchbase.Lite;
using Couchbase.Lite.P2P;
using System.Net;
using System.Security.Cryptography.X509Certificates;
using System.Text.Json;
using JetBrains.Annotations;
using TestServer.Utilities;

namespace TestServer.Handlers;


internal static partial class HandlerList
{
    [SuppressMessage("ReSharper", "InconsistentNaming")]
    internal readonly record struct TLSIdentityData
    {
        public required string encoding { get; init; }

        public required string data { get; init; }

        [UsedImplicitly]
        public string? password { get; init; }
    }

    [SuppressMessage("ReSharper", "InconsistentNaming")]
    internal readonly record struct StartListenerBody
    {
        public required string database { get; init; }

        public required string[] collections { get; init; }

        [UsedImplicitly]
        public ushort port { get; init; }

        [UsedImplicitly]
        public bool disableTLS { get; init; }

        [UsedImplicitly]
        public TLSIdentityData? identity { get; init; }
    }

    private static TLSIdentity? CreateOrReuseTLSIdentity(TLSIdentityData? identityData, string label)
    {
        using var store = new X509Store(StoreName.My, StoreLocation.CurrentUser);
        store.Open(OpenFlags.ReadWrite);

        if (identityData.HasValue) {
            var incoming = identityData.Value;
            if (!string.Equals(incoming.encoding, "PKCS12", StringComparison.OrdinalIgnoreCase)) {
                throw new JsonException(
                    $"Unsupported TLS identity encoding '{incoming.encoding}' (expected PKCS12)");
            }

            var pfxBytes = Convert.FromBase64String(incoming.data);

            // Match the iOS behavior: clear any stale identity so a re-import under the
            // same label doesn't collide.
            TLSIdentity.DeleteIdentity(store, label, null);

            return TLSIdentity.ImportIdentity(store, pfxBytes, incoming.password, label, null);
        }

        return TLSIdentity.GetIdentity(store, label, null);
    }

    [HttpHandler("startListener")]
    public static async Task StartListenerHandler(Session session, JsonDocument body, HttpListenerResponse response)
    {
        if (!body.RootElement.TryDeserialize<StartListenerBody>(out var deserializedBody, out var ex)) {
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

        var collectionObjects = new List<Collection>();
        foreach(var c in deserializedBody.collections) {
            var collSpec = CollectionSpec(c);
            var collection = dbObject.GetCollection(collSpec.name, collSpec.scope)
                ?? throw new JsonException($"Collection {c} does not exist in db!");
            collectionObjects.Add(collection);
        }

        TLSIdentity? tlsIdentity = null;

        if (!deserializedBody.disableTLS) {
            var label = $"dotnet-p2p-{deserializedBody.database}";

            try {
                tlsIdentity = CreateOrReuseTLSIdentity(deserializedBody.identity, label);
            } catch (Exception e) {
                var errorObject = new
                {
                    domain = (int)CouchbaseLiteErrorType.CouchbaseLite + 1,
                    code = (int)CouchbaseLiteError.NotFound,
                    message = $"Failed to import TLS identity for label '{label}': {e.Message}"
                };

                await response.WriteBody(errorObject, HttpStatusCode.BadRequest).ConfigureAwait(false);
                return;
            }

            if (tlsIdentity == null) {
                var errorObject = new
                {
                    domain = (int)CouchbaseLiteErrorType.CouchbaseLite + 1,
                    code = (int)CouchbaseLiteError.NotFound,
                    message = $"TLS enabled but no existing TLS identity found for label '{label}'"
                };

                await response.WriteBody(errorObject, HttpStatusCode.BadRequest).ConfigureAwait(false);
                return;
            }
        }
        var listenerConfig = new URLEndpointListenerConfiguration(collectionObjects)
        {
            Port = deserializedBody.port,
            DisableTLS = deserializedBody.disableTLS,
            TlsIdentity = tlsIdentity
        };

        var (listener, id) = session.ObjectManager.RegisterObject(() => new URLEndpointListener(listenerConfig));
        listener.Start();

        var responseBody = new Dictionary<string, object>
        {
            { "id", id },
            { "port", listener.Port }
        };

        await response.WriteBody(responseBody).ConfigureAwait(false);
    }
}
