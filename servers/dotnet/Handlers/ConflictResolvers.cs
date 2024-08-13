using Couchbase.Lite;

namespace TestServer.Handlers;

internal sealed class LocalWinsConflictResolver : IConflictResolver
{
    public Document? Resolve(Conflict conflict)
    {
        return conflict.LocalDocument;
    }
}

internal sealed class RemoteWinsConflictResolver : IConflictResolver
{
    public Document? Resolve(Conflict conflict)
    {
        return conflict.RemoteDocument;
    }
}
