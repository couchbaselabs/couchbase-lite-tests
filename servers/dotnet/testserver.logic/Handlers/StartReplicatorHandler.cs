using Couchbase.Lite;
using Couchbase.Lite.Sync;
using System.Collections;
using System.Collections.Immutable;
using System.Diagnostics.CodeAnalysis;
using System.Net;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;
using JetBrains.Annotations;
using TestServer.Utilities;

namespace TestServer.Handlers;
using FilterGenerator = Func<IReadOnlyDictionary<string, JsonElement>?, HandlerList.IReplicatorFilter>;
using FilterFunction = Func<Document, DocumentFlags, bool>;

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
        private const string DOCUMENT_IDS_KEY = "documentIDs";
        
        private readonly Dictionary<string, IReadOnlySet<string>> _allowedDocumentIDs;

        public ReplicatorDocumentIDsFilter(IReadOnlyDictionary<string, JsonElement>? args)
        {
            if(args?.ContainsKey(DOCUMENT_IDS_KEY) == false) {
                throw new ApplicationStatusException("documentIDs filter is missing documentIDs argument", HttpStatusCode.BadRequest);
            }

            if (args![DOCUMENT_IDS_KEY].ValueKind != JsonValueKind.Object) {
                throw new ApplicationStatusException("documentIDs filter documentIDs argument wrong type (expecting dictionary of arrays)",
                    HttpStatusCode.BadRequest);
            }

            _allowedDocumentIDs = args[DOCUMENT_IDS_KEY].EnumerateObject().ToDictionary(x => x.Name, IReadOnlySet<string> (x) =>
            {
                if (x.Value.ValueKind != JsonValueKind.Array) {
                    throw new ApplicationStatusException($"documentIDs filter documentIDs argument contained invalid list for '{x.Name}'",
                        HttpStatusCode.BadRequest);
                }

                return x.Value.EnumerateArray().Select(y => y.ToString()).ToHashSet();
            });
        }

        public bool Execute(Document doc, DocumentFlags flags)
        {
            if(doc.Collection == null) {
                throw new ApplicationStatusException("Document had null collection in filter", HttpStatusCode.InternalServerError);
            }

            return _allowedDocumentIDs.TryGetValue(doc.Collection.FullName, out var d) && d.Contains(doc.Id);
        }
    }

    [SuppressMessage("ReSharper", "InconsistentNaming")]
    internal readonly record struct DocumentReplicationEvent
    {
        [UsedImplicitly]
        public required bool isPush { get; init; }

        [UsedImplicitly]
        public required string collection { get; init; }

        [UsedImplicitly]
        public required string documentID { get; init; }

        [UsedImplicitly]
        public required IReadOnlyList<string> flags { get; init; }

        [UsedImplicitly]
        public ErrorReturnBody? error { get; init; }
    }

    internal sealed class ReplicatorDocumentListener : IDisposable, IEnumerable<DocumentReplicationEvent>
    {
        private readonly ListenerToken _listenerToken;
        private List<DocumentReplicationEventArgs> _events = [];

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

                    yield return new()
                    {
                        isPush = entry.IsPush,
                        collection = $"{doc.ScopeName}.{doc.CollectionName}",
                        documentID = doc.Id,
                        flags = [doc.Flags == 0 ? "None" : doc.Flags.ToString()],
                        error = error
                    };
                }
            }
        }

        IEnumerator IEnumerable.GetEnumerator() => GetEnumerator();
    }

    [SuppressMessage("ReSharper", "InconsistentNaming")]
    internal readonly record struct StartReplicatorAuthenticator
    {
        private const string BasicType = "BASIC";

        // Note that System.Text.Json does not support private fields or properties
        // ReSharper disable MemberCanBePrivate.Global
        public readonly string username = "";
        public readonly string password = "";
        // ReSharper restore MemberCanBePrivate.Global

        public required string type { get; init; }

        [JsonConstructor]
        public StartReplicatorAuthenticator(string type, string? username = null, string? password = null)
        {
            this.type = type;
            if (type != BasicType) {
                return;
            }

            this.username = username ?? throw new JsonException("Missing username property in auth");
            this.password = password ?? throw new JsonException("Missing password property in auth");
        }

        public Authenticator CreateAuthenticator()
        {
            return type == BasicType
                ? new BasicAuthenticator(username, password)
                : throw new NotImplementedException("Non-BASIC auth not implemented");
        }
    }

    [SuppressMessage("ReSharper", "InconsistentNaming")]
    [method: JsonConstructor]
    internal record StartReplicatorFilter(
        string name,
        [property: JsonPropertyName("params")] IReadOnlyDictionary<string, JsonElement>? parameters = null)
    {
        public required string name { get; init; } = name;
    }

    [SuppressMessage("ReSharper", "InconsistentNaming")]
    [method: JsonConstructor]
    internal record StartReplicatorConflictResolver(
        string name,
        [property: JsonPropertyName("params")] IReadOnlyDictionary<string, JsonElement>? parameters = null)
    {
        public required string name { get; init; } = name;
    }

    [SuppressMessage("ReSharper", "InconsistentNaming")]
    internal readonly record struct StartReplicatorCollection
    {
        public required IReadOnlyList<string> names { get; init; }
        
        [UsedImplicitly]
        public IReadOnlyList<string> channels { get; init; }
        
        [UsedImplicitly]
        public IReadOnlyList<string> documentIDs { get; init; }
        
        [UsedImplicitly]
        public StartReplicatorFilter? pushFilter { get; init; }
        
        [UsedImplicitly]
        public StartReplicatorFilter? pullFilter { get; init; }
        
        [UsedImplicitly]
        public StartReplicatorConflictResolver? conflictResolver { get; init; }
        
        public IConflictResolver? ConflictResolver { get; }

        [JsonConstructor]
        public StartReplicatorCollection(IReadOnlyList<string> names, IReadOnlyList<string?>? channels = null,
             IReadOnlyList<string?>? documentIDs = null, StartReplicatorFilter? pushFilter = null, StartReplicatorFilter? pullFilter = null,
             StartReplicatorConflictResolver? conflictResolver = null)
        {
            this.names = names;
            this.channels = channels.NotNull().ToList();
            this.documentIDs = documentIDs.NotNull().ToList();
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


    [SuppressMessage("ReSharper", "InconsistentNaming")]
    internal readonly record struct StartReplicatorConfig
    {
        public required string database { get; init; }

        public required string endpoint { get; init; }

        public required bool continuous { get; init; }
        
        [UsedImplicitly]
        public required string replicatorType { get; init; }

        public required IReadOnlyList<StartReplicatorCollection> collections { get; init; }

        [UsedImplicitly]
        public StartReplicatorAuthenticator? authenticator { get; init; }

        public ReplicatorType ReplicatorType { get; }

        [UsedImplicitly]
        public bool enableDocumentListener { get; init; }

        [UsedImplicitly]
        public bool enableAutoPurge { get; init; }

        [UsedImplicitly]
        public string? pinnedServerCert { get; init; }

        [UsedImplicitly]
        public IReadOnlyDictionary<string, string?>? headers { get; init; }

        [JsonConstructor]
        public StartReplicatorConfig(string database, string endpoint,
            string replicatorType, bool continuous, IReadOnlyList<StartReplicatorCollection> collections,
            StartReplicatorAuthenticator? authenticator = null, bool enableDocumentListener = false,
            bool enableAutoPurge = true, string? pinnedServerCert = null, IReadOnlyDictionary<string, string?>? headers = null)
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
            this.headers = headers;

            if (replicatorType.Equals("pull", StringComparison.InvariantCultureIgnoreCase)) {
                ReplicatorType = ReplicatorType.Pull;
            } else if (replicatorType.Equals("push", StringComparison.InvariantCultureIgnoreCase)) {
                ReplicatorType = ReplicatorType.Push;
            } else if (replicatorType.Equals("pushandpull", StringComparison.InvariantCultureIgnoreCase)) {
                ReplicatorType = ReplicatorType.PushAndPull;
            } else {
                throw new JsonException($"Invalid replicatorType '{replicatorType}' (expecting push, pull, or pushAndPull)");
            }
        }
    }

    [SuppressMessage("ReSharper", "InconsistentNaming")]
    [method: JsonConstructor]
    internal readonly record struct StartReplicatorBody(StartReplicatorConfig config, bool reset = false)
    {
        public required StartReplicatorConfig config { get; init; } = config;
    }

    private static FilterFunction? GetFilter(Session session, StartReplicatorFilter? input)
    {
        if (input is null) {
            return null;
        }

        if(!ReplicatorFilters.FilterMap.TryGetValue(input.name, out var filterGen)) {
            throw new JsonException($"Unknown push filter {input.name}");
        }

        var filter = filterGen(input.parameters);
        session.ObjectManager.KeepAlive(filter);
        return filter.Execute;
    }

    [HttpHandler("startReplicator")]
    public static async Task StartReplicatorHandler(Session session, JsonDocument body, HttpListenerResponse response)
    {
        if(!body.RootElement.TryDeserialize<StartReplicatorBody>(out var deserializedBody, out var ex)) {
            await response.WriteDeserializationError(ex).ConfigureAwait(false);
            return;
        }

        var db = session.ObjectManager.GetDatabase(deserializedBody.config.database);
        if (db == null) {
            await response.WriteBody(Router.CreateErrorResponse($"Unable to find db named '{deserializedBody.config.database}'!"), HttpStatusCode.BadRequest).ConfigureAwait(false);
            return;
        }

        var endpoint = new URLEndpoint(new Uri(deserializedBody.config.endpoint));
        var collectionConfigs = new List<CollectionConfiguration>();
        if (deserializedBody.config.collections.Any()) {
            foreach (var c in deserializedBody.config.collections) {
                foreach(var name in c.names) {
                    var spec = CollectionSpec(name);
                    var coll = db.GetCollection(spec.name, spec.scope);
                    if (coll == null) {
                        await response.WriteBody(Router.CreateErrorResponse($"Unable to find collection '{name}'"), HttpStatusCode.BadRequest).ConfigureAwait(false);
                        return;
                    }

                    var collectionConfig = new CollectionConfiguration(coll)
                    {
                        Channels = c.channels.Any() ? c.channels.ToImmutableList() : null,
                        DocumentIDs = c.documentIDs.Any() ? c.documentIDs.ToImmutableList() : null,
                        PushFilter = GetFilter(session, c.pushFilter),
                        PullFilter = GetFilter(session, c.pullFilter),
                        ConflictResolver = c.ConflictResolver
                    };
                    collectionConfigs.Add(collectionConfig);
                }
            }
        } else {
            collectionConfigs = CollectionConfiguration.FromCollections(db.GetDefaultCollection());
        }

        var replConfig = new ReplicatorConfiguration(collectionConfigs, endpoint)
        {
            Authenticator = deserializedBody.config.authenticator?.CreateAuthenticator(),
            Continuous = deserializedBody.config.continuous,
            ReplicatorType = deserializedBody.config.ReplicatorType,
            EnableAutoPurge = deserializedBody.config.enableAutoPurge,
            PinnedServerCertificate = deserializedBody.config.pinnedServerCert != null
                ? new(Encoding.ASCII.GetBytes(deserializedBody.config.pinnedServerCert))
                : null,
            Headers = deserializedBody.config.headers?.ToImmutableDictionary() ?? ImmutableDictionary<string, string?>.Empty,
        };

        var (repl, id) = session.ObjectManager.RegisterObject(() => new Replicator(replConfig));
        if(deserializedBody.config.enableDocumentListener) {
            session.ObjectManager.RegisterObject(() => new ReplicatorDocumentListener(repl), $"{id}_listener");
        }

        repl.Start(deserializedBody.reset);

        await response.WriteBody(new { id }).ConfigureAwait(false);
    }
}
