using System.Diagnostics.CodeAnalysis;
using Couchbase.Lite;
using System.Net;
using System.Text.Json;
using JetBrains.Annotations;
using TestServer.Utilities;

namespace TestServer.Handlers;

[UsedImplicitly]
[SuppressMessage("ReSharper", "InconsistentNaming")]
internal readonly record struct AllDocumentsResponse(string id, string rev);

internal static partial class HandlerList
{
    [HttpHandler("getAllDocuments")]
    [UsedImplicitly]
    public static async Task AllDocumentsHandler(Session session, JsonDocument body, HttpListenerResponse response)
    {
        if(!body.RootElement.TryGetProperty("database", out var database) || database.ValueKind != JsonValueKind.String) {
            await response.WriteBody(Router.CreateErrorResponse("'database' property not found or invalid"), 
                HttpStatusCode.BadRequest).ConfigureAwait(false);
            return;
        }

        if(!body.RootElement.TryGetProperty("collections", out var collections) || collections.ValueKind != JsonValueKind.Array) {
            await response.WriteBody(Router.CreateErrorResponse("'collections' property not found or invalid"), 
                HttpStatusCode.BadRequest).ConfigureAwait(false);
            return;
        }

        var dbName = database.GetString()!;
        var dbObject = session.ObjectManager.GetDatabase(dbName);
        if(dbObject == null) {
            var errorObject = new
            {
                domain = (int)CouchbaseLiteErrorType.CouchbaseLite + 1,
                code = (int)CouchbaseLiteError.NotFound,
                message = $"database '{dbName}' not registered!"
            };

            await response.WriteBody(errorObject, HttpStatusCode.BadRequest).ConfigureAwait(false);
            return;
        }

        var retVal = new Dictionary<string, List<AllDocumentsResponse>>();
        foreach(var collName in collections.EnumerateArray()
            .Where(x => x.ValueKind == JsonValueKind.String)
            .Select(x => x.GetString()!)) {
            using var q = dbObject.CreateQuery($"SELECT meta().id, meta().revisionID FROM {collName}");
            var results = q.Execute().Select(x => new AllDocumentsResponse(x.GetString(0)!, x.GetString(1)!)).ToList();
            retVal[collName] = results;
        }

        await response.WriteBody(retVal).ConfigureAwait(false);
    }
}
