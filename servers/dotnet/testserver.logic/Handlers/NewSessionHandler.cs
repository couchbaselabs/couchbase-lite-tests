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
using TestServer.Utilities;

namespace TestServer.Handlers;

internal sealed class LogSlurpSink : ILogEventSink
{
    private ClientWebSocket _ws = new();
    private ManualResetEventSlim _connectWait = new();
    private ManualResetEventSlim _sendWait = new();
    private readonly ITextFormatter _formatter;

    public LogSlurpSink(string url, string id, string tag, ITextFormatter textFormatter)
    {
        _ws.Options.SetRequestHeader("CBL-Log-ID", id);
        _ws.Options.SetRequestHeader("CBL-Log-Tag", tag);
        _formatter = textFormatter;
        _ws.ConnectAsync(new Uri($"ws://{url}/openLogStream"), CancellationToken.None)
            .ContinueWith(t => _connectWait.Set());
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
            .ContinueWith(t => _sendWait.Set());

        if (!_sendWait.Wait(TimeSpan.FromSeconds(5))) {
            throw new TimeoutException("LogSlurpSink hung on send");
        }
    }
}

internal static class SerilogExtensions 
{
    internal const string DefaultSlurpOutputTemplate = "[{@l:u3}]: {@m}\n{@x}";

    public static LoggerConfiguration LogSlurp(this LoggerSinkConfiguration config, string url, string id, string tag,
        string outputTemplate = DefaultSlurpOutputTemplate)
    {
        return config.Sink(new LogSlurpSink(url, id, tag, new ExpressionTemplate(outputTemplate)));
    }
}

internal record NewSessionLoggingInfo(string url, string tag);

internal readonly record struct NewSessionBody(string id, NewSessionLoggingInfo? logging);

internal static partial class HandlerList
{
    private static Serilog.ILogger? Original = null;

    [HttpHandler("newSession", noSession: true)]
    public static Task NewSessionHandler(int version, JsonDocument body, HttpListenerResponse response)
    {
        if (!body.RootElement.TryDeserialize<NewSessionBody>(response, version, out var newSessionBody)) {
            return Task.CompletedTask;
        }

        Session.Create(CBLTestServer.ServiceProvider, newSessionBody.id);

        if(newSessionBody.logging == null) {
            response.WriteEmptyBody(version);
            return Task.CompletedTask;
        }

        // A little trick I learned from Serilog.  Instead of trying to mess with the existing
        // configurations, create a new one that logs to the existing one AND the new sink
        if(Original == null) {
            Original = Log.Logger;
        }

        Log.Logger = new LoggerConfiguration()
            .WriteTo.Logger(Original)
            .WriteTo.LogSlurp(newSessionBody.logging.url, newSessionBody.id, newSessionBody.logging.tag)
            .CreateLogger();

        Log.Information("Test server consolidated logging started");

        response.WriteEmptyBody(version);
        return Task.CompletedTask;
    }
}