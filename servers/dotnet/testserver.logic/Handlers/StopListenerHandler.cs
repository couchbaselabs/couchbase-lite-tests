using System.Diagnostics.CodeAnalysis;
using Couchbase.Lite;
using Couchbase.Lite.P2P;
using System.Net;
using System.Text.Json;
using TestServer.Utilities;

namespace TestServer.Handlers;


internal static partial class HandlerList
{
    [SuppressMessage("ReSharper", "InconsistentNaming")]
    internal readonly record struct StopListenerBody
    {
        public required string id { get; init; }
    }

    [HttpHandler("stopListener")]
    public static async Task StopListenerHandler(Session session, JsonDocument body, HttpListenerResponse response)
    {
        if (!body.RootElement.TryDeserialize<StopListenerBody>(out var deserializedBody, out var ex)) {
            await response.WriteDeserializationError(ex).ConfigureAwait(false);
            return;
        }

        var listenerObject = session.ObjectManager.GetObject<URLEndpointListener>(deserializedBody.id);
        if (listenerObject == null) {
            var errorObject = new
            {
                domain = (int)CouchbaseLiteErrorType.CouchbaseLite + 1,
                code = (int)CouchbaseLiteError.NotFound,
                message = $"listener with specified ID not registered!"
            };

            await response.WriteBody(errorObject, HttpStatusCode.BadRequest).ConfigureAwait(false);
            return;
        }

        listenerObject.Stop();
        await response.WriteEmptyBody().ConfigureAwait(false);
    }
}
