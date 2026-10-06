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
var port = CBLTestServer.DEFAULT_PORT;
for (var i = 0; i < args.Length; i++) {
    var arg = args[i];
    if (arg == "--silent") {
        silent = true;
    } else if (arg == "--port") {
        if (i + 1 >= args.Length) {
            Console.Error.WriteLine("Error: Missing value for --port");
            PrintUsage();
            return 1;
        }

        if (!TryParsePort(args[++i], out port)) {
            return 1;
        }
    } else if (UInt16.TryParse(arg, out var positionalPort) && positionalPort != 0) {
        // A bare port, the form this server has always accepted.
        port = positionalPort;
    } else {
        Console.Error.WriteLine($"Error: Unrecognized argument: {arg}");
        PrintUsage();
        return 1;
    }
}

var collection = new ServiceCollection();
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

var server = new CBLTestServer()
{
    Port = port
};

_ = server.Start();

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
return 0;

void Log(string message)
{
    if(silent) {
        return;
    }

    Console.WriteLine(message);
}

static bool TryParsePort(string value, out ushort port)
{
    if (!UInt16.TryParse(value, out port) || port == 0) {
        Console.Error.WriteLine($"Error: Invalid --port value: \"{value}\" (expected an integer in 1..65535)");
        PrintUsage();
        return false;
    }

    return true;
}

// Argument errors are printed even under --silent: they happen before the logger exists, and a
// server that never bound the port it was asked for must not look like a successful start.
static void PrintUsage() => Console.Error.WriteLine("Usage: testserver.cli [--silent] [--port <port>]");

static bool IsInterfaceValid(NetworkInterface ni)
{
    if (ni.OperationalStatus != OperationalStatus.Up) {
        return false;
    }

    if (ni.NetworkInterfaceType == NetworkInterfaceType.Loopback || ni.NetworkInterfaceType == NetworkInterfaceType.Tunnel
                                                                 || ni.Description.Contains("Loopback", StringComparison.OrdinalIgnoreCase)) {
        return false;
    }

    return !ni.Description.Contains("virtual", StringComparison.OrdinalIgnoreCase);
}
