using Couchbase.Lite;
using System.Collections.Specialized;
using System.Diagnostics;
using System.Net;
using System.Text.Json;

namespace TestServer.Handlers;

internal readonly record struct AllDocumentsResponse(string id, string rev);

internal static partial class HandlerList
{
    [HttpHandler("getAllDocuments")]
    public static void AllDocumentsHandler(int version, JsonDocument body, HttpListenerResponse response)
    {
        if(!body.RootElement.TryGetProperty("database", out var database) || database.ValueKind != JsonValueKind.String) {
            response.WriteBody(Router.CreateErrorResponse("'database' property not found or invalid"), version, HttpStatusCode.BadRequest);
            return;
        }

        if(!body.RootElement.TryGetProperty("collections", out var collections) || collections.ValueKind != JsonValueKind.Array) {
            response.WriteBody(Router.CreateErrorResponse("'collections' property not found or invalid"), version, HttpStatusCode.BadRequest);
            return;
        }

        var dbName = database.GetString()!;
        var dbObject = CBLTestServer.Manager.GetDatabase(dbName);
        if(dbObject == null) {
            var errorObject = new
            {
                domain = (int)CouchbaseLiteErrorType.CouchbaseLite + 1,
                code = (int)CouchbaseLiteError.NotFound,
                message = $"database '{dbName}' not registered!"
            };

            response.WriteBody(errorObject, version, HttpStatusCode.BadRequest);
            return;
        }



        var retVal = new Dictionary<string, List<AllDocumentsResponse>>();
        foreach(var collName in collections.EnumerateArray()
            .Where(x => x.ValueKind == JsonValueKind.String)
            .Select(x => x.GetString()!)) {
            using var q = dbObject.CreateQuery($"SELECT meta().id, meta().revisionID FROM {collName}");
            var results = q.Execute().Select(x => new AllDocumentsResponse(x.GetString(0)!, x.GetString(1)!)).ToList();
            if(results.Any()) {
                retVal[collName] = results;
            }
        }

        response.WriteBody(retVal, version);
    }
}
