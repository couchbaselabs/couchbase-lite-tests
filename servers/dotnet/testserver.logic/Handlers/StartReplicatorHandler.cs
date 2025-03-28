﻿using Couchbase.Lite;
using Couchbase.Lite.Sync;
using System.Collections;
using System.Net;
using System.Security.Cryptography.X509Certificates;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;
using TestServer.Utilities;

namespace TestServer.Handlers;
using FilterGenerator = Func<IReadOnlyDictionary<string, JsonElement>?, HandlerList.IReplicatorFilter>;

internal static partial class HandlerList
{
    internal interface IReplicatorFilter
    {
        bool Execute(Document doc, DocumentFlags flags);
    }

    internal static class ReplicatorFilters
    {
        public static readonly IReadOnlyDictionary<string, FilterGenerator> FilterMap =
            new Dictionary<string, FilterGenerator>
        {
            ["deletedDocumentsOnly"] = (_) => new ReplicatorDeletedOnlyFilter(),
            ["documentIDs"] = (args) => new ReplicatorDocumentIDsFilter(args)
        };
    }

    internal sealed class ReplicatorDeletedOnlyFilter : IReplicatorFilter
    {
        public bool Execute(Document doc, DocumentFlags flags)
        {
            return flags.HasFlag(DocumentFlags.Deleted);
        }
    }

    internal sealed class ReplicatorDocumentIDsFilter : IReplicatorFilter
    {
        private const string DocumentIDsKey = "documentIDs";
        private Dictionary<string, IReadOnlySet<string>> _allowedDocumentIDs;

        public ReplicatorDocumentIDsFilter(IReadOnlyDictionary<string, JsonElement>? args)
        {
            if(args?.ContainsKey(DocumentIDsKey) == false) {
                throw new ApplicationStatusException("documentIDs filter is missing documentIDs argument", HttpStatusCode.BadRequest);
            }

            if (args![DocumentIDsKey].ValueKind != JsonValueKind.Object) {
                throw new ApplicationStatusException("documentIDs filter documentIDs argument wrong type (expecting dictionary of arrays)",
                    HttpStatusCode.BadRequest);
            }

            _allowedDocumentIDs = args[DocumentIDsKey].EnumerateObject().ToDictionary(x => x.Name, x =>
            {
                if (x.Value.ValueKind != JsonValueKind.Array) {
                    throw new ApplicationStatusException($"documentIDs filter documentIDs argument contained invalid list for '{x.Name}'",
                        HttpStatusCode.BadRequest);
                }

                return (IReadOnlySet<string>)x.Value.EnumerateArray().Select(x => x.ToString()).ToHashSet();
            });
        }

        public bool Execute(Document doc, DocumentFlags flags)
        {
            if(doc.Collection == null) {
                throw new ApplicationStatusException("Document had null collection in filter", HttpStatusCode.InternalServerError);
            }

            if(!_allowedDocumentIDs.ContainsKey(doc.Collection.FullName)) {
                return false;
            }

            return _allowedDocumentIDs[doc.Collection.FullName].Contains(doc.Id);
        }
    }

    internal readonly record struct DocumentReplicationEvent
    {
        public required bool isPush { get; init; }

        public required string collection { get; init; }

        public required string documentID { get; init; }

        public required IReadOnlyList<string> flags { get; init; }

        public ErrorReturnBody? error { get; init; }
    }

    internal sealed class ReplicatorDocumentListener : IDisposable, IEnumerable<DocumentReplicationEvent>
    {
        private ListenerToken _listenerToken;
        private List<DocumentReplicationEventArgs> _events = new List<DocumentReplicationEventArgs>();

        public ReplicatorDocumentListener(Replicator replicator)
        {
            _listenerToken = replicator.AddDocumentReplicationListener(HandleChange);
        }



        private void HandleChange(object? sender, DocumentReplicationEventArgs e)
        {
            _events.Add(e);
        }

        public void Dispose()
        {
            try {
                _listenerToken.Remove();
            } catch(ObjectDisposedException) {
                // Replicator already disposed, no need to do anything else
            }
        }

        public IEnumerator<DocumentReplicationEvent> GetEnumerator()
        {
            var events = Interlocked.Exchange(ref _events, new List<DocumentReplicationEventArgs>());
            foreach (var entry in events) {
                foreach (var doc in entry.Documents) {
                    ErrorReturnBody? error = null;
                    if(doc.Error != null) {
                        var details = Router.MapError(doc.Error);
                        error = new ErrorReturnBody
                        {
                            code = details.code,
                            domain = details.domain,
                            message = doc.Error.Message
                        };
                    }

                    yield return new DocumentReplicationEvent
                    {
                        isPush = entry.IsPush,
                        collection = $"{doc.ScopeName}.{doc.CollectionName}",
                        documentID = doc.Id,
                        flags = new[] { doc.Flags == 0 ? "None" : doc.Flags.ToString() },
                        error = error
                    };
                }
            }
        }

        IEnumerator IEnumerable.GetEnumerator()
        {
            return ((IEnumerable<DocumentReplicationEvent>)this).GetEnumerator();
        }
    }

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

    internal record class StartReplicatorFilter
    {
        public required string name { get; init; }

        [JsonPropertyName("params")]
        public IReadOnlyDictionary<string, JsonElement>? parameters { get; init; }

        [JsonConstructor]
        public StartReplicatorFilter(string name, IReadOnlyDictionary<string, JsonElement>? parameters = null)
        {
            this.name = name;
            this.parameters = parameters;
        }
    }

    internal record class StartReplicatorConflictResolver
    {
        public required string name { get; init; }

        [JsonPropertyName("params")]
        public IReadOnlyDictionary<string, JsonElement>? parameters { get; init; }

        [JsonConstructor]
        public StartReplicatorConflictResolver(string name, IReadOnlyDictionary<string, JsonElement>? parameters = null)
        {
            this.name = name;
            this.parameters = parameters;
        }
    }

    internal readonly record struct StartReplicatorCollection
    {
        public required IReadOnlyList<string> names { get; init; }
        public IReadOnlyList<string> channels { get; init; }
        public IReadOnlyList<string> documentIDs { get; init; }
        public StartReplicatorFilter? pushFilter { get; init; }
        public StartReplicatorFilter? pullFilter { get; init; }
        public StartReplicatorConflictResolver? conflictResolver { get; init; }
        public IConflictResolver? ConflictResolver { get; }

        [JsonConstructor]
        public StartReplicatorCollection(IReadOnlyList<string> names, IReadOnlyList<string?>? channels = default,
             IReadOnlyList<string?>? documentIDs = default, StartReplicatorFilter? pushFilter = null, StartReplicatorFilter? pullFilter = null,
             StartReplicatorConflictResolver? conflictResolver = null)
        {
            this.names = names;
            this.channels = channels.NotNull().ToList() ?? new List<string>();
            this.documentIDs = documentIDs.NotNull().ToList() ?? new List<string>();
            this.pushFilter = pushFilter;
            this.pullFilter = pullFilter;
            this.conflictResolver = conflictResolver;
            switch(conflictResolver?.name) {
                case null:
                    break;
                case "local-wins":
                    ConflictResolver = new LocalWinsConflictResolver();
                    break;
                case "remote-wins":
                    ConflictResolver = new RemoteWinsConflictResolver();
                    break;
                case "delete":
                    ConflictResolver = new DeleteConflictResolver();
                    break;
                case "merge":
                    ConflictResolver = new MergeConflictResolver(conflictResolver.parameters);
                    break;
                default:
                    throw new JsonException($"Bad conflict resolver choice {conflictResolver}");
            }
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

        public bool enableDocumentListener { get; init; }

        public bool enableAutoPurge { get; init; }

        public string? pinnedServerCert { get; init; }

        [JsonConstructor]
        public StartReplicatorConfig(string database, string endpoint,
            string replicatorType, bool continuous, IReadOnlyList<StartReplicatorCollection> collections,
            StartReplicatorAuthenticator? authenticator = null, bool enableDocumentListener = false,
            bool enableAutoPurge = true, string? pinnedServerCert = null)
        {
            this.database = database;
            this.endpoint = endpoint;
            this.replicatorType = replicatorType;
            this.continuous = continuous;
            this.collections = collections;
            this.authenticator = authenticator;
            this.enableDocumentListener = enableDocumentListener;
            this.enableAutoPurge = enableAutoPurge;
            this.pinnedServerCert = pinnedServerCert;

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
    public static Task StartReplicatorHandler(int version, Session session, JsonDocument body, HttpListenerResponse response)
    {
        if(!body.RootElement.TryDeserialize<StartReplicatorBody>(response, version, out var deserializedBody)) {
            return Task.CompletedTask;
        }

        var db = session.ObjectManager.GetDatabase(deserializedBody.config.database);
        if (db == null) {
            response.WriteBody(Router.CreateErrorResponse($"Unable to find db named '{deserializedBody.config.database}'!"), version, HttpStatusCode.BadRequest);
            return Task.CompletedTask;
        }

        ReplicatorConfiguration replConfig;
        var endpoint = new URLEndpoint(new Uri(deserializedBody.config.endpoint));
        if (deserializedBody.config.collections.Any()) {
            replConfig = new ReplicatorConfiguration(endpoint);
            foreach (var c in deserializedBody.config.collections) {
                var collections = new List<Collection>();
                foreach(var name in c.names) {
                    var spec = CollectionSpec(name);
                    var coll = db.GetCollection(spec.name, spec.scope);
                    if (coll == null) {
                        response.WriteBody(Router.CreateErrorResponse($"Unable to find collection '{name}'"), version, HttpStatusCode.BadRequest);
                        return Task.CompletedTask;
                    }

                    collections.Add(coll);
                }
                

                var collConfig = new CollectionConfiguration();
                if(c.channels.Any()) {
                    collConfig.Channels = c.channels.ToList();
                }

                if(c.documentIDs.Any()) {
                    collConfig.DocumentIDs = c.documentIDs.ToList();
                }

                if(c.pushFilter != null) {
                    if(!ReplicatorFilters.FilterMap.ContainsKey(c.pushFilter.name)) {
                        throw new JsonException($"Unknown push filter {c.pushFilter.name}");
                    }

                    var filter = ReplicatorFilters.FilterMap[c.pushFilter.name](c.pushFilter.parameters);
                    session.ObjectManager.KeepAlive(filter);
                    collConfig.PushFilter = filter.Execute;
                }

                if(c.pullFilter != null) {
                    if (!ReplicatorFilters.FilterMap.ContainsKey(c.pullFilter.name)) {
                        throw new JsonException($"Unknown push filter {c.pullFilter.name}");
                    }

                    var filter = ReplicatorFilters.FilterMap[c.pullFilter.name](c.pullFilter.parameters);
                    session.ObjectManager.KeepAlive(filter);
                    collConfig.PullFilter = filter.Execute;
                }

                collConfig.ConflictResolver = c.ConflictResolver;

                replConfig.AddCollections(collections, collConfig);
            }
        } else {
            replConfig = new ReplicatorConfiguration(db, endpoint);
        }

        replConfig.Authenticator = deserializedBody.config.authenticator?.CreateAuthenticator();
        replConfig.Continuous = deserializedBody.config.continuous;
        replConfig.ReplicatorType = deserializedBody.config.ReplicatorType;
        replConfig.EnableAutoPurge = deserializedBody.config.enableAutoPurge;
        if (deserializedBody.config.pinnedServerCert != null) {
            replConfig.PinnedServerCertificate = new X509Certificate2(Encoding.ASCII.GetBytes(deserializedBody.config.pinnedServerCert));
        }

        (var repl, var id) = session.ObjectManager.RegisterObject(() => new Replicator(replConfig));
        if(deserializedBody.config.enableDocumentListener) {
            var listener = new ReplicatorDocumentListener(repl);
            session.ObjectManager.RegisterObject(() => new ReplicatorDocumentListener(repl), $"{id}_listener");
        }

        repl.Start(deserializedBody.reset);

        response.WriteBody(new { id }, version);
        return Task.CompletedTask;
    }
}