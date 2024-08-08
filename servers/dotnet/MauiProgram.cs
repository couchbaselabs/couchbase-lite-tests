using Couchbase.Lite.Logging;
using Microsoft.Extensions.Logging;
using Serilog;
using Serilog.Core;
using Serilog.Events;
using System.Diagnostics;
using TestServer.Platforms;

namespace TestServer;

public sealed class SerilogLogger : Couchbase.Lite.Logging.ILogger
{
	private readonly Logger _serilogLogger;

	public SerilogLogger(Logger serilogLogger)
	{
		_serilogLogger = serilogLogger;
	}

	public Couchbase.Lite.Logging.LogLevel Level => Couchbase.Lite.Logging.LogLevel.Debug;

    public void Log(Couchbase.Lite.Logging.LogLevel level, LogDomain domain, string message)
    {
		var outLevel = LogEventLevel.Information;
		switch(level) {
			case Couchbase.Lite.Logging.LogLevel.Debug:
				outLevel = LogEventLevel.Debug;
				break;
			case Couchbase.Lite.Logging.LogLevel.Verbose:
				outLevel = LogEventLevel.Verbose;
				break;
			case Couchbase.Lite.Logging.LogLevel.Warning:
				outLevel = LogEventLevel.Warning;
				break;
			case Couchbase.Lite.Logging.LogLevel.Error:
				outLevel = LogEventLevel.Error;
				break;
			case Couchbase.Lite.Logging.LogLevel.None:
				return;
			default:
				break;
		}

		_serilogLogger.Write(outLevel, "[{domain}] {msg}", domain, message);
    }
}

public static class MauiProgram
{
	public static IServiceProvider ServiceProvider { get; private set; } = default!;

	public static string LogFilePath { get; private set; } = default!;

	public static MauiApp CreateMauiApp()
	{
		var builder = MauiApp.CreateBuilder();
		builder
			.UseMauiApp<App>()
			.AddTestServerServices()
			.ConfigureFonts(fonts =>
			{
				fonts.AddFont("OpenSans-Regular.ttf", "OpenSansRegular");
				fonts.AddFont("OpenSans-Semibold.ttf", "OpenSansSemibold");
			});

		LogFilePath = $"{Path.GetTempFileName()}.txt";
		var logConfig = new LoggerConfiguration()
			.MinimumLevel.Debug()
			.WriteTo.File(LogFilePath)
			.WriteTo.Console(restrictedToMinimumLevel: LogEventLevel.Warning);

#if DEBUG
		logConfig.WriteTo.Debug(restrictedToMinimumLevel: LogEventLevel.Warning);
#endif

		var logger = logConfig.CreateLogger();
		builder.Logging.AddSerilog(logger, true);
		logger.Write(LogEventLevel.Information, "Test server started at {time}", DateTimeOffset.UtcNow);

		Couchbase.Lite.Database.Log.Custom = new SerilogLogger(logger);
		Couchbase.Lite.Database.Log.Console.Level = Couchbase.Lite.Logging.LogLevel.None;

		Console.WriteLine($"Beginning combined server/cbl log to {LogFilePath}");
        Debug.WriteLine($"Beginning combined server/cbl log to {LogFilePath}");

        var retVal = builder.Build();
		ServiceProvider = retVal.Services;
		return retVal;
	}
}
