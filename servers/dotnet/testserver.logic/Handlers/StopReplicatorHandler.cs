using Couchbase.Lite.Sync;
using System.Net;
using System.Text.Json;

namespace TestServer.Handlers;

internal static partial class HandlerList
{
    internal readonly record struct StopReplicatorConfig(string id);

    [HttpHandler("stopReplicator")]
    public static Task StopReplicatorHandler(int version, JsonDocument body, HttpListenerResponse response)
    {
        if (!body.RootElement.TryDeserialize<StopReplicatorConfig>(response, version, out var deserializedBody)) {
            return Task.CompletedTask;
        }

        var replicator = CBLTestServer.Manager.GetObject<Replicator>(deserializedBody.id);
        if(replicator == null) {
            throw new JsonException($"Replicator with ID '{deserializedBody.id}' does not exist!");
        }

        replicator.Stop();

        response.WriteEmptyBody(version);
        return Task.CompletedTask;
    }
}