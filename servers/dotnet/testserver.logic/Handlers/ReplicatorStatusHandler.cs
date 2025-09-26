using System.Diagnostics.CodeAnalysis;
using Couchbase.Lite;
using Couchbase.Lite.Sync;
using System.Net;
using System.Text.Json;
using System.Text.Json.Serialization;
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
    internal readonly record struct ReplicatorProgressReturnBody(bool completed);

    [SuppressMessage("ReSharper", "InconsistentNaming")]
    internal readonly record struct ErrorReturnBody(string domain, int code, string message);

    [SuppressMessage("ReSharper", "InconsistentNaming")]
    internal record struct ReplicatorStatusReturnBody(string activity, ReplicatorProgressReturnBody progress, 
        IReadOnlyList<DocumentReplicationEvent> documents, ErrorReturnBody? error = null);

    [HttpHandler("getReplicatorStatus")]
    public static Task ReplicatorStatusHandler(int version, Session session, JsonDocument body, HttpListenerResponse response)
    {
        if(!body.RootElement.TryDeserialize<ReplicatorStatusBody>(response, version, out var replicatorStatusBody)) {
            return Task.CompletedTask;
        }

        var replicator = session.ObjectManager.GetObject<Replicator>(replicatorStatusBody.id);
        if(replicator == null) {
            response.WriteBody(Router.CreateErrorResponse($"Unable to find replicator with id '{replicatorStatusBody.id}'"), version, HttpStatusCode.BadRequest);
            return Task.CompletedTask;
        }

        var activity = replicator.Status.Activity.ToString().ToUpperInvariant();
        var complete = replicator.Status.Progress.Total == replicator.Status.Progress.Completed;
        ErrorReturnBody? error = null;

        if(replicator.Status.Error is CouchbaseException couchbaseEx && couchbaseEx != null) {
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
        response.WriteBody(retVal, version);
        return Task.CompletedTask;
    }
}