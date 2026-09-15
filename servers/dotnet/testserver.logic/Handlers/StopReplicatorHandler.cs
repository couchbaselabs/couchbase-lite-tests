using System.Diagnostics.CodeAnalysis;
using Couchbase.Lite.Sync;
using System.Net;
using System.Text.Json;
using TestServer.Utilities;

namespace TestServer.Handlers;

internal static partial class HandlerList
{
    [SuppressMessage("ReSharper", "InconsistentNaming")]
    internal readonly record struct StopReplicatorConfig
    {
        public required string id { get; init; }
    }

    [HttpHandler("stopReplicator")]
    public static async Task StopReplicatorHandler(Session session, JsonDocument body, HttpListenerResponse response)
    {
        if (!body.RootElement.TryDeserialize<StopReplicatorConfig>(out var deserializedBody, out var ex)) {
            await response.WriteDeserializationError(ex).ConfigureAwait(false);
            return;
        }

        var replicator = session.ObjectManager.GetObject<Replicator>(deserializedBody.id);
        if(replicator == null) {
            throw new JsonException($"Replicator with ID '{deserializedBody.id}' does not exist!");
        }

        replicator.Stop();

        await response.WriteEmptyBody().ConfigureAwait(false);
    }
}
