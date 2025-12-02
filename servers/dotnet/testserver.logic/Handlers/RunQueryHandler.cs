using System;
using System.Collections.Generic;
using System.Linq;
using System.Net;
using System.Text;
using System.Text.Json;
using System.Threading.Tasks;
using TestServer.Utilities;

namespace TestServer.Handlers;

internal static partial class HandlerList
{
    internal readonly record struct RunQueryBody(string database, string query);

    [HttpHandler("runQuery")]
    public static Task RunQueryHandler(Session session, JsonDocument body, HttpListenerResponse response)
    {
        if (!body.RootElement.TryDeserialize<RunQueryBody>(response, out var runQueryBody)) {
            return Task.CompletedTask;
        }

        var db = session.ObjectManager.GetDatabase(runQueryBody.database);
        if (db == null) {
            response.WriteBody(Router.CreateErrorResponse($"Unable to find database named '{runQueryBody.database}'"), HttpStatusCode.BadRequest);
            return Task.CompletedTask;
        }

        using var query = db.CreateQuery(runQueryBody.query);
        using var results = query.Execute();
        var retVal = new
        {
            results = results.Select(x => x.ToDictionary())
        };

        response.WriteBody(retVal);
        return Task.CompletedTask;
    }
}

