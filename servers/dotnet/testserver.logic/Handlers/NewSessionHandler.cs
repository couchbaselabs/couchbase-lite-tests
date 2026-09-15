using System.Diagnostics.CodeAnalysis;
using Serilog;
using Serilog.Configuration;
using Serilog.Core;
using Serilog.Events;
using Serilog.Formatting;
using Serilog.Templates;
using System.Net;
using System.Net.WebSockets;
using System.Text;
using System.Text.Json;
using JetBrains.Annotations;
using TestServer.Utilities;

namespace TestServer.Handlers;

internal sealed class LogSlurpSink : ILogEventSink
{
    private readonly ClientWebSocket _ws = new();
    private readonly ManualResetEventSlim _connectWait = new();
    private readonly ManualResetEventSlim _sendWait = new();
    private readonly ITextFormatter _formatter;

    public LogSlurpSink(string url, string id, string tag, ITextFormatter textFormatter)
    {
        _ws.Options.SetRequestHeader("CBL-Log-ID", id);
        _ws.Options.SetRequestHeader("CBL-Log-Tag", tag);
        _formatter = textFormatter;
        _ws.ConnectAsync(new Uri($"ws://{url}/openLogStream"), CancellationToken.None)
            .ContinueWith(_ => _connectWait.Set());
    }

    public void Emit(LogEvent logEvent)
    {
        if (!_connectWait.Wait(TimeSpan.FromSeconds(5))) {
            throw new TimeoutException("LogSlurpSink hung on connect");
        }

        _sendWait.Reset();
        using var sw = new StringWriter();
        _formatter.Format(logEvent, sw);
        _ws.SendAsync(Encoding.UTF8.GetBytes(sw.ToString().TrimEnd()), WebSocketMessageType.Text, true, CancellationToken.None)
            .ContinueWith(_ => _sendWait.Set());

        if (!_sendWait.Wait(TimeSpan.FromSeconds(5))) {
            throw new TimeoutException("LogSlurpSink hung on send");
        }
    }
}

internal static class SerilogExtensions
{
    private const string DEFAULT_SLURP_OUTPUT_TEMPLATE = "[{@l:u3}]: {@m}\n{@x}";

    public static LoggerConfiguration LogSlurp(this LoggerSinkConfiguration config, string url, string id, string tag,
        string outputTemplate = DEFAULT_SLURP_OUTPUT_TEMPLATE)
    {
        return config.Sink(new LogSlurpSink(url, id, tag, new ExpressionTemplate(outputTemplate)));
    }
}

[UsedImplicitly]
[SuppressMessage("ReSharper", "InconsistentNaming")]
internal record NewSessionLoggingInfo(string url, string tag);

[SuppressMessage("ReSharper", "InconsistentNaming")]
internal readonly record struct NewSessionBody(string id, NewSessionLoggingInfo? logging = null);

internal static partial class HandlerList
{
    private static ILogger? Original;

    [HttpHandler("newSession", noSession: true)]
    [UsedImplicitly]
    public static async Task NewSessionHandler(JsonDocument body, HttpListenerResponse response)
    {
        if (!body.RootElement.TryDeserialize<NewSessionBody>(out var newSessionBody, out var ex)) {
            await response.WriteDeserializationError(ex).ConfigureAwait(false);
            return;
        }

        Session.Create(CBLTestServer.ServiceProvider, newSessionBody.id);

        if(newSessionBody.logging == null) {
            await response.WriteEmptyBody().ConfigureAwait(false);
            return;
        }

        // A little trick I learned from Serilog.  Instead of trying to mess with the existing
        // configurations, create a new one that logs to the existing one AND the new sink
        Original ??= Log.Logger;

        Log.Logger = new LoggerConfiguration()
            .MinimumLevel.Verbose()
            .WriteTo.Logger(Original)
            .WriteTo.LogSlurp(newSessionBody.logging.url, newSessionBody.id, newSessionBody.logging.tag)
            .CreateLogger();

        Log.Information("Test server consolidated logging started");

        await response.WriteEmptyBody().ConfigureAwait(false);
    }
}
