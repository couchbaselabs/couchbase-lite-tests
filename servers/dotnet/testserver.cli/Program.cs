using Microsoft.Extensions.DependencyInjection;
using Serilog.Events;
using Serilog;
using System.Net.NetworkInformation;
using System.Net.Sockets;
using System.Reflection;
using TestServer;
using TestServer.Cli.Services;
using TestServer.Services;
using TestServer.Utilities;
using Couchbase.Lite.Logging;

var silent = false;
ushort port = 0;
foreach (var arg in args) {
    if (arg == "--silent") {
        silent = true;
    } else {
        port = UInt16.Parse(arg);
    }
}

ServiceCollection collection = new ServiceCollection();
collection.AddSingleton<IDeviceInformation, DeviceInformation>();
collection.AddSingleton<IFileSystem, CLIFileSystem>();

var logFilePath = $"{Path.GetTempFileName()}.txt";
var logConfig = new LoggerConfiguration()
    .MinimumLevel.Debug()
    .WriteTo.File(logFilePath);

if(!silent) {
    logConfig.WriteTo.Console(restrictedToMinimumLevel: LogEventLevel.Warning);
}

#if DEBUG
logConfig.WriteTo.Debug(restrictedToMinimumLevel: LogEventLevel.Warning);
#endif

Serilog.Log.Logger = logConfig.CreateLogger();
Serilog.Log.Logger.Write(LogEventLevel.Information, "Test server started at {time}", DateTimeOffset.UtcNow);

LogSinks.Custom = new SerilogLogger(LogLevel.Debug);
LogSinks.Console = null;

CBLTestServer.ServiceProvider = collection.BuildServiceProvider();

static bool IsInterfaceValid(NetworkInterface ni)
{
    if (ni.OperationalStatus != OperationalStatus.Up) {
        return false;
    }

    if (ni.NetworkInterfaceType == NetworkInterfaceType.Loopback || ni.NetworkInterfaceType == NetworkInterfaceType.Tunnel
        || ni.Description.IndexOf("Loopback", StringComparison.OrdinalIgnoreCase) >= 0) {
        return false;
    }

    if (ni.Description.IndexOf("virtual", StringComparison.OrdinalIgnoreCase) >= 0) {
        return false;
    }

    return true;
}

var server = new CBLTestServer()
{
    Port = port
};
var _ = server.Start();
void Log(string message)
{
    if(silent) {
        return;
    }

    Console.WriteLine(message);
}

Log($"Test Server Version: {CBLTestServer.Version}");
Log("CBL Version: " + typeof(Couchbase.Lite.Database).Assembly.GetCustomAttribute<AssemblyInformationalVersionAttribute>()!.InformationalVersion);
var validIPs = NetworkInterface.GetAllNetworkInterfaces().Where(IsInterfaceValid)
                    .SelectMany(x => x.GetIPProperties().UnicastAddresses)
                    .Where(x => x.Address.AddressFamily == AddressFamily.InterNetwork && x.Address.GetAddressBytes()[0] != 169);

var ipAddresses = "Server running at:" +
    Environment.NewLine +
    String.Join(Environment.NewLine, validIPs
    .Select(x => $"http://{x.Address}:{server.Port}"));
Log(ipAddresses);

await Task.Delay(Timeout.Infinite);

server.Stop();
