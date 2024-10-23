
using System.Net;
using System.Text.Json;
using TestServer.Utilities;

namespace TestServer.Handlers;

internal readonly record struct LogHandlerBody
{
    public required string message { get; init; }
}

internal static partial class HandlerList
{
    [HttpHandler("log")]
    public static Task LogHandler(int version, Session session, JsonDocument body, HttpListenerResponse response)
    {
        if (!body.RootElement.TryDeserialize<LogHandlerBody>(response, version, out var logBody)) {
            return Task.CompletedTask;
        }

        Serilog.Log.Logger.Information(logBody.message);

        response.WriteEmptyBody(version);
        return Task.CompletedTask;
    }
}