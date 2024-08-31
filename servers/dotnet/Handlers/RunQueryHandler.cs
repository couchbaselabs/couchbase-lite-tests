using System;
using System.Collections.Generic;
using System.Linq;
using System.Net;
using System.Text;
using System.Text.Json;
using System.Threading.Tasks;

namespace TestServer.Handlers;

internal static partial class HandlerList
{
    internal readonly record struct RunQueryBody(string database, string query);

    [HttpHandler("runQuery")]
    public static Task RunQueryHandler(int version, JsonDocument body, HttpListenerResponse response)
    {
        if (!body.RootElement.TryDeserialize<RunQueryBody>(response, version, out var runQueryBody)) {
            return Task.CompletedTask;
        }

        var db = CBLTestServer.Manager.GetDatabase(runQueryBody.database);
        if (db == null) {
            response.WriteBody(Router.CreateErrorResponse($"Unable to find database named '{runQueryBody.database}'"), version, HttpStatusCode.BadRequest);
            return Task.CompletedTask;
        }

        using var query = db.CreateQuery(runQueryBody.query);
        using var results = query.Execute();
        var retVal = new
        {
            results = results.Select(x => x.ToDictionary())
        };

        response.WriteBody(retVal, version);
        return Task.CompletedTask;
    }
}

