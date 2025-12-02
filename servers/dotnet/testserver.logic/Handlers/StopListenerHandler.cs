using Couchbase.Lite;
using Couchbase.Lite.P2P;
using System.Net;
using System.Text.Json;
using TestServer.Utilities;

namespace TestServer.Handlers;


internal static partial class HandlerList
{
    internal readonly record struct StopListenerBody
    {
        public required string id { get; init; }
    }

    [HttpHandler("stopListener")]
    public static Task StopListenerHandler(Session session, JsonDocument body, HttpListenerResponse response)
    {
        if (!body.RootElement.TryDeserialize<StopListenerBody>(response, out var deserializedBody)) {
            return Task.CompletedTask;
        }

        var listenerObject = session.ObjectManager.GetObject<URLEndpointListener>(deserializedBody.id);
        if (listenerObject == null) {
            var errorObject = new
            {
                domain = (int)CouchbaseLiteErrorType.CouchbaseLite + 1,
                code = (int)CouchbaseLiteError.NotFound,
                message = $"listener with specified ID not registered!"
            };

            response.WriteBody(errorObject, HttpStatusCode.BadRequest);
            return Task.CompletedTask;
        }

        listenerObject.Stop();
        response.WriteEmptyBody();
        return Task.CompletedTask;
    }
}
