using Couchbase.Lite.Logging;
using Serilog.Events;

namespace TestServer.Utilities
{
    public sealed class SerilogLogger : ILogger
    {
        public SerilogLogger()
        {
        }

        public LogLevel Level => LogLevel.Debug;

        public void Log(LogLevel level, LogDomain domain, string message)
        {
            var outLevel = LogEventLevel.Information;
            switch (level) {
                case LogLevel.Debug:
                    outLevel = LogEventLevel.Debug;
                    break;
                case LogLevel.Verbose:
                    outLevel = LogEventLevel.Verbose;
                    break;
                case LogLevel.Warning:
                    outLevel = LogEventLevel.Warning;
                    break;
                case LogLevel.Error:
                    outLevel = LogEventLevel.Error;
                    break;
                case LogLevel.None:
                    return;
                default:
                    break;
            }

            Serilog.Log.Logger.Write(outLevel, "[{domain}] {msg}", domain, message);
        }
    }
}
