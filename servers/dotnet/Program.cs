#if HEADLESS

using System.Net.Sockets;
using System.Net;
using System.Reflection;
using TestServer;
using TestServer.Services;
using System.Runtime.InteropServices;

var server = new CBLTestServer();
var _ = server.Start();
var version = "CBL Version: " + typeof(Couchbase.Lite.Database).Assembly.GetCustomAttribute<AssemblyInformationalVersionAttribute>()!.InformationalVersion;
Console.WriteLine(version);
var host = Dns.GetHostEntry(Dns.GetHostName());
var ipAddresses = "Server running at:" +
    Environment.NewLine +
    String.Join(Environment.NewLine, host.AddressList
    .Where(x => x.AddressFamily == AddressFamily.InterNetwork)
    .Select(x => $"http://{x}:8080"));
Console.WriteLine(ipAddresses);
Console.ReadKey(true);
server.Stop();
Console.WriteLine("Server stopped...");

internal sealed class DeviceInformation : IDeviceInformation
{
    public string Model => $"{RuntimeInformation.OSArchitecture} Desktop";

    public string SystemName
    {
        get {
            if (RuntimeInformation.IsOSPlatform(OSPlatform.Windows)) {
                return "Windows";
            }

            if (RuntimeInformation.IsOSPlatform(OSPlatform.OSX)) {
                return "macOS";
            }

            if (RuntimeInformation.IsOSPlatform(OSPlatform.Linux)) {
                return "Linux";
            }

            return "Unknown";
        }
    }

    public string SystemVersion => RuntimeInformation.OSDescription;

    public string SystemApiVersion => RuntimeInformation.OSDescription;
}

internal static class FileSystem
{
    public static string AppDataDirectory => AppContext.BaseDirectory;

    public static Task<Stream> OpenAppPackageFileAsync(string path)
    {
        return Task.Run<Stream>(() =>
        {
            return File.OpenRead(Path.Combine(AppDataDirectory, path));
        });
    }
}

#endif