using Couchbase.Lite;
using System.Collections.Specialized;
using System.Diagnostics;
using System.Net;
using System.Text.Json;

namespace TestServer.Handlers;

internal static partial class HandlerList
{
    public static void AllDocumentIDsHandler(NameValueCollection args, JsonDocument body, HttpListenerResponse response)
    {
        if(!body.RootElement.TryGetProperty("database", out var database) || database.ValueKind != JsonValueKind.String) {
            response.WriteBody(Router.CreateErrorResponse("'database' property not found or invalid"), HttpStatusCode.BadRequest);
            return;
        }

        if(!body.RootElement.TryGetProperty("collections", out var collections) || collections.ValueKind != JsonValueKind.Array) {
            response.WriteBody(Router.CreateErrorResponse("'collections' property not found or invalid"), HttpStatusCode.BadRequest);
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

            response.WriteBody(errorObject, HttpStatusCode.BadRequest);
            return;
        }

        var retVal = new Dictionary<string, List<string>>();
        foreach(var collName in collections.EnumerateArray()
            .Where(x => x.ValueKind == JsonValueKind.String)
            .Select(x => x.GetString()!)) {
            using var q = dbObject.CreateQuery($"SELECT meta().id FROM {collName}");
            var results = q.Execute().Select(x => x.GetString(0)!).ToList();
            if(results.Any()) {
                retVal[collName] = results;
            }
        }

        response.WriteBody(retVal);
    }
}
