using System.Diagnostics.CodeAnalysis;
using System.Net;
using System.Text.Json;
using TestServer.Utilities;

namespace TestServer.Handlers;

internal static partial class HandlerList
{
    [SuppressMessage("ReSharper", "InconsistentNaming")]
    internal readonly record struct RunQueryBody(string database, string query);

    [HttpHandler("runQuery")]
    public static async Task RunQueryHandler(Session session, JsonDocument body, HttpListenerResponse response)
    {
        if (!body.RootElement.TryDeserialize<RunQueryBody>(out var runQueryBody, out var ex)) {
            await response.WriteDeserializationError(ex).ConfigureAwait(false);
            return;
        }

        var db = session.ObjectManager.GetDatabase(runQueryBody.database);
        if (db == null) {
            await response.WriteBody(Router.CreateErrorResponse($"Unable to find database named '{runQueryBody.database}'"), HttpStatusCode.BadRequest).ConfigureAwait(false);
            return;
        }

        using var query = db.CreateQuery(runQueryBody.query);
        using var results = query.Execute();
        var retVal = new
        {
            results = results.Select(x => x.ToDictionary())
        };

        await response.WriteBody(retVal).ConfigureAwait(false);
    }
}

