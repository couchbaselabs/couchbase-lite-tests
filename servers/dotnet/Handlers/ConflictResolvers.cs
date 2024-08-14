using Couchbase.Lite;
using Serilog;
using System.Text.Json;

namespace TestServer.Handlers;

internal sealed class LocalWinsConflictResolver : IConflictResolver
{
    public Document? Resolve(Conflict conflict) => conflict.LocalDocument;
}

internal sealed class RemoteWinsConflictResolver : IConflictResolver
{
    public Document? Resolve(Conflict conflict) => conflict.RemoteDocument;
}

internal sealed class DeleteConflictResolver : IConflictResolver
{
    public Document? Resolve(Conflict conflict) => null;
}

internal sealed class MergeConflictResolver : IConflictResolver
{
    private readonly string _property;

    public MergeConflictResolver(IReadOnlyDictionary<string, JsonElement>? properties)
    {
        if(properties == null) {
            throw new JsonException("Missing params from 'merge' conflictResolver");
        }

        if(!properties.TryGetValue("property", out var tmp)) {
            throw new JsonException("Missing 'property' param from params");
        }

        var propertyName = tmp.GetString();
        if(propertyName == null) {
            throw new JsonException("Invalid 'property' param, must be a string");
        }

        if(propertyName.Contains('.')) {
            throw new JsonException("Invalid 'property' param, must be top-level");
        }

        _property = propertyName;
    }

    public Document? Resolve(Conflict conflict)
    {
        var left = conflict.LocalDocument?.GetValue(_property);
        var right = conflict.RemoteDocument?.GetValue(_property);

        var retVal = conflict.LocalDocument?.ToMutable() ?? conflict.RemoteDocument?.ToMutable();
        if(retVal == null) {
            Log.Logger.Warning("Both local and remote are null in merge resolve, returning null...");
            return null;
        }

        retVal.SetValue(_property, new MutableArrayObject().AddValue(left).AddValue(right));
        return retVal;
    }
}
