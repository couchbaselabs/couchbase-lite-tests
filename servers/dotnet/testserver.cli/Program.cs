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

ServiceCollection collection = new ServiceCollection();
collection.AddSingleton<IDeviceInformation, DeviceInformation>();
collection.AddSingleton<IFileSystem, CLIFileSystem>();

var logFilePath = $"{Path.GetTempFileName()}.txt";
var logConfig = new LoggerConfiguration()
    .MinimumLevel.Debug()
    .WriteTo.File(logFilePath)
    .WriteTo.Console(restrictedToMinimumLevel: LogEventLevel.Warning);

#if DEBUG
logConfig.WriteTo.Debug(restrictedToMinimumLevel: LogEventLevel.Warning);
#endif

Serilog.Log.Logger = logConfig.CreateLogger();
Serilog.Log.Logger.Write(LogEventLevel.Information, "Test server started at {time}", DateTimeOffset.UtcNow);

Couchbase.Lite.Database.Log.Custom = new SerilogLogger();
Couchbase.Lite.Database.Log.Console.Level = LogLevel.None;

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

var server = new CBLTestServer();
server.Start();

Console.WriteLine("CBL Version: " + typeof(Couchbase.Lite.Database).Assembly.GetCustomAttribute<AssemblyInformationalVersionAttribute>()!.InformationalVersion);
var validIPs = NetworkInterface.GetAllNetworkInterfaces().Where(IsInterfaceValid)
                    .SelectMany(x => x.GetIPProperties().UnicastAddresses)
                    .Where(x => x.Address.AddressFamily == AddressFamily.InterNetwork && x.Address.GetAddressBytes()[0] != 169);

var ipAddresses = "Server running at:" +
    Environment.NewLine +
    String.Join(Environment.NewLine, validIPs
    .Select(x => $"http://{x.Address}:8080"));
Console.WriteLine(ipAddresses);
Console.WriteLine("Press any key to exit at any time...");

Console.ReadKey();

server.Stop();