using Couchbase.Lite.Logging;
using Serilog;
using Serilog.Events;
using System.Diagnostics;
using TestServer.Platforms;

namespace TestServer;

public sealed class SerilogLogger : Couchbase.Lite.Logging.ILogger
{
	public SerilogLogger()
	{
	}

	public LogLevel Level => LogLevel.Debug;

    public void Log(LogLevel level, LogDomain domain, string message)
    {
		var outLevel = LogEventLevel.Information;
		switch(level) {
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

		Serilog.Log.Logger = logConfig.CreateLogger();
        Serilog.Log.Logger.Write(LogEventLevel.Information, "Test server started at {time}", DateTimeOffset.UtcNow);

		Couchbase.Lite.Database.Log.Custom = new SerilogLogger();
		Couchbase.Lite.Database.Log.Console.Level = LogLevel.None;

		Console.WriteLine($"Beginning combined server/cbl log to {LogFilePath}");
        Debug.WriteLine($"Beginning combined server/cbl log to {LogFilePath}");

        var retVal = builder.Build();
		ServiceProvider = retVal.Services;
		return retVal;
	}
}
