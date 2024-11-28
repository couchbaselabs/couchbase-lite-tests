using Couchbase.Lite.Logging;
using Serilog;
using Serilog.Events;
using System.Diagnostics;
using TestServer.Platforms;
using TestServer.Services;
using TestServer.Utilities;
using IFileSystem = TestServer.Services.IFileSystem;

namespace TestServer;

public static class MauiProgram
{
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

		builder.Services.AddSingleton<IFileSystem, MauiFileSystem>();

		LogFilePath = $"{Path.GetTempFileName()}.txt";
		var logConfig = new LoggerConfiguration()
			.MinimumLevel.Verbose()
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
		CBLTestServer.ServiceProvider = retVal.Services;
		return retVal;
	}
}
