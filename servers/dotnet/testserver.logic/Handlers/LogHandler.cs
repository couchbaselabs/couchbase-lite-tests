
using System.Diagnostics.CodeAnalysis;
using System.Net;
using System.Text.Json;
using JetBrains.Annotations;
using TestServer.Utilities;

namespace TestServer.Handlers;

[SuppressMessage("ReSharper", "InconsistentNaming")]
internal readonly record struct LogHandlerBody
{
    public required string message { get; init; }
}

internal static partial class HandlerList
{
    [HttpHandler("log")]
    [UsedImplicitly]
    public static async Task LogHandler(Session session, JsonDocument body, HttpListenerResponse response)
    {
        if (!body.RootElement.TryDeserialize<LogHandlerBody>(out var logBody, out var ex)) {
            await response.WriteDeserializationError(ex).ConfigureAwait(false);
            return;
        }

        Serilog.Log.Logger.Information("{msg}", logBody.message);
        await response.WriteEmptyBody().ConfigureAwait(false);
    }
}
