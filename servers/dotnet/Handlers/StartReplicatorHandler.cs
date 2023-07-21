using Couchbase.Lite;
using Couchbase.Lite.Sync;
using System.Collections.Specialized;
using System.Diagnostics.CodeAnalysis;
using System.Net;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace TestServer.Handlers;

internal static partial class HandlerList
{
    internal readonly record struct StartReplicatorAuthenticator
    {
        private const string BasicType = "BASIC";

        // Note that System.Text.Json does not support private fields or properties
        public readonly string username = "";
        public readonly string password = "";

        public required string type { get; init; }

        [JsonConstructor]
        public StartReplicatorAuthenticator(string type, string? username = null, string? password = null)
        {
            this.type = type;
            if(type == BasicType) {
                this.username = username ?? throw new JsonException("Missing username property in auth");
                this.password = password ?? throw new JsonException("Missing password property in auth");
            }
        }

        public Authenticator CreateAuthenticator()
        {
            if(type == BasicType) {
                return new BasicAuthenticator(username, password);
            }

            throw new NotImplementedException("Non-BASIC auth not implemented");
        }
    }

    internal readonly record struct StartReplicatorCollection
    {
        public required string collection { get; init; }
        public IReadOnlyList<string> channels { get; init; }
        public IReadOnlyList<string> documentIDs { get; init; }

        [JsonConstructor]
        public StartReplicatorCollection(string collection, IReadOnlyList<string?>? channels = default,
             IReadOnlyList<string?>? documentIDs = default)
        {
            this.collection = collection;
            this.channels = channels.NotNull().ToList() ?? new List<string>();
            this.documentIDs = documentIDs.NotNull().ToList() ?? new List<string>();
        }
    }


    internal readonly record struct StartReplicatorConfig
    {
        public required string database { get; init; }

        public required string endpoint { get; init; }

        public required bool continuous { get; init; }

        public required string replicatorType { get; init; }

        public required IReadOnlyList<StartReplicatorCollection> collections { get; init; }

        public StartReplicatorAuthenticator? authenticator { get; init; }

        public ReplicatorType ReplicatorType { get; }

        [JsonConstructor]
        public StartReplicatorConfig(string database, string endpoint,
            string replicatorType, bool continuous, IReadOnlyList<StartReplicatorCollection> collections,
            StartReplicatorAuthenticator? authenticator = null)
        {
            this.database = database;
            this.endpoint = endpoint;
            this.continuous = continuous;
            this.collections = collections;
            this.authenticator = authenticator;

            if (replicatorType.ToLowerInvariant() == "pull") {
                ReplicatorType = ReplicatorType.Pull;
            } else if (replicatorType.ToLowerInvariant() == "push") {
                ReplicatorType = ReplicatorType.Push;
            } else if (replicatorType.ToLowerInvariant() == "pushandpull") {
                ReplicatorType = ReplicatorType.PushAndPull;
            } else {
                throw new JsonException($"Invalid replicatorType '{replicatorType}' (expecting push, pull, or pushAndPull)");
            }
        }
    } 

    internal readonly record struct StartReplicatorBody
    {
        public required StartReplicatorConfig config { get; init; }

        public bool reset { get; init; }

        [JsonConstructor]
        public StartReplicatorBody(StartReplicatorConfig config, bool reset = false)
        {
            this.config = config;
            this.reset = reset;
        }
    }

    [HttpHandler("startReplicator")]
    public static void StartReplicatorHandler(int version, JsonDocument body, HttpListenerResponse response)
    {
        if(!body.RootElement.TryDeserialize<StartReplicatorBody>(response, version, out var deserializedBody)) {
            return;
        }

        var db = CBLTestServer.Manager.GetDatabase(deserializedBody.config.database);
        if (db == null) {
            response.WriteBody(Router.CreateErrorResponse($"Unable to find db named '{deserializedBody.config.database}'!"), version, HttpStatusCode.BadRequest);
            return;
        }

        ReplicatorConfiguration replConfig;
        var endpoint = new URLEndpoint(new Uri(deserializedBody.config.endpoint));
        if (deserializedBody.config.collections.Any()) {
            replConfig = new ReplicatorConfiguration(endpoint);
            foreach(var c in deserializedBody.config.collections) {
                var spec = CollectionSpec(c.collection);
                var coll = db.GetCollection(spec.name, spec.scope);
                if(coll == null) {
                    response.WriteBody(Router.CreateErrorResponse($"Unable to find collection '{c.collection}'"), version, HttpStatusCode.BadRequest);
                    return;
                }

                var collConfig = new CollectionConfiguration();
                if(c.channels.Any()) {
                    collConfig.Channels = c.channels.ToList();
                }

                if(c.documentIDs.Any()) {
                    collConfig.DocumentIDs = c.documentIDs.ToList();
                }

                replConfig.AddCollection(coll, collConfig);
            }
        } else {
            replConfig = new ReplicatorConfiguration(db, endpoint);
        }

        replConfig.Authenticator = deserializedBody.config.authenticator?.CreateAuthenticator();

        (var repl, var id) = CBLTestServer.Manager.RegisterObject(() => new Replicator(replConfig));
        repl.Start();

        response.WriteBody(new { id }, version);
    }
}