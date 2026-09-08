using System.Diagnostics.CodeAnalysis;
using Couchbase.Lite;
using Couchbase.Lite.Sync;
using System.Net;
using System.Text.Json;
using System.Text.Json.Serialization;
using JetBrains.Annotations;
using TestServer.Utilities;

namespace TestServer.Handlers;

internal static partial class HandlerList
{
    [SuppressMessage("ReSharper", "InconsistentNaming")]
    [method: JsonConstructor]
    internal readonly record struct ReplicatorStatusBody(string id)
    {
        public required string id { get; init; } = id;
    }

    [SuppressMessage("ReSharper", "InconsistentNaming")]
    [UsedImplicitly] 
    internal readonly record struct ReplicatorProgressReturnBody(bool completed);

    [SuppressMessage("ReSharper", "InconsistentNaming")]
    [UsedImplicitly] 
    internal readonly record struct ErrorReturnBody(string domain, int code, string message);

    [SuppressMessage("ReSharper", "InconsistentNaming")]
    [UsedImplicitly] 
    internal record struct ReplicatorStatusReturnBody(string activity, ReplicatorProgressReturnBody progress,
        IReadOnlyList<DocumentReplicationEvent> documents, ErrorReturnBody? error = null);

    [HttpHandler("getReplicatorStatus")]
    public static async Task ReplicatorStatusHandler(Session session, JsonDocument body, HttpListenerResponse response)
    {
        if(!body.RootElement.TryDeserialize<ReplicatorStatusBody>(out var replicatorStatusBody, out var ex)) {
            await response.WriteDeserializationError(ex).ConfigureAwait(false);
            return;
        }

        var replicator = session.ObjectManager.GetObject<Replicator>(replicatorStatusBody.id);
        if(replicator == null) {
            await response.WriteBody(Router.CreateErrorResponse($"Unable to find replicator with id '{replicatorStatusBody.id}'"), HttpStatusCode.BadRequest).ConfigureAwait(false);
            return;
        }

        var activity = replicator.Status.Activity.ToString().ToUpperInvariant();
        var complete = replicator.Status.Progress.Total == replicator.Status.Progress.Completed;
        ErrorReturnBody? error = null;

        if(replicator.Status.Error is CouchbaseException couchbaseEx) {
            var (domain, code) = Router.MapError(couchbaseEx);
            error = new ErrorReturnBody
            {
                domain = domain,
                code = code,
                message = couchbaseEx.Message
            };
        }

        var docs = new List<DocumentReplicationEvent>();
        var listener = session.ObjectManager.GetObject<ReplicatorDocumentListener>($"{replicatorStatusBody.id}_listener");
        if(listener != null) {
            docs = listener.ToList();
        }

        var retVal = new ReplicatorStatusReturnBody(activity, new ReplicatorProgressReturnBody(complete), docs, error);
        await response.WriteBody(retVal).ConfigureAwait(false);
    }
}
