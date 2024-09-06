using Couchbase.Lite;
using Couchbase.Lite.Sync;
using Newtonsoft.Json;
using System;
using System.Collections.Generic;
using System.Collections.Specialized;
using System.Dynamic;
using System.Linq;
using System.Net;
using System.Reflection;
using System.Text;
using System.Text.Json;
using System.Threading.Tasks;
using TestServer.Services;

namespace TestServer.Handlers;

internal static partial class HandlerList
{
    internal readonly record struct ReplicatorStatusBody
    {
        public required string id { get; init; }

        [JsonConstructor]
        public ReplicatorStatusBody(string id)
        {
            this.id = id;
        }
    }

    internal readonly record struct ReplicatorProgressReturnBody(bool completed);

    internal readonly record struct ErrorReturnBody(string domain, int code, string message);

    internal record struct ReplicatorStatusReturnBody(string activity, ReplicatorProgressReturnBody progress, 
        IReadOnlyList<DocumentReplicationEvent> documents, ErrorReturnBody? error = null);

    [HttpHandler("getReplicatorStatus")]
    public static Task ReplicatorStatusHandler(int version, JsonDocument body, HttpListenerResponse response)
    {
        if(!body.RootElement.TryDeserialize<ReplicatorStatusBody>(response, version, out var replicatorStatusBody)) {
            return Task.CompletedTask;
        }

        var replicator = CBLTestServer.Manager.GetObject<Replicator>(replicatorStatusBody.id);
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
        var listener = CBLTestServer.Manager.GetObject<ReplicatorDocumentListener>($"{replicatorStatusBody.id}_listener");
        if(listener != null) {
            docs = listener.ToList();
        }

        var retVal = new ReplicatorStatusReturnBody(activity, new ReplicatorProgressReturnBody(complete), docs, error);
        response.WriteBody(retVal, version);
        return Task.CompletedTask;
    }
}