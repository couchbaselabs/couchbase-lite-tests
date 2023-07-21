using System.Collections.Specialized;
using System.Net;
using System.Reflection;
using System.Text.Json;
using TestServer.Services;

namespace TestServer.Handlers;

internal static partial class HandlerList
{
    [HttpHandler("")]
    public static void GetRootHandler(int version, JsonDocument body, HttpListenerResponse response)
    {
        var resolvedVersion = version != 0 ? version : CBLTestServer.MaxApiVersion;
        var responseBody = new
        {
            version = typeof(Couchbase.Lite.Database).Assembly.GetCustomAttribute<AssemblyInformationalVersionAttribute>()?.InformationalVersion,
            apiVersion = resolvedVersion,
            cbl = "couchbase-lite-net",
            device = ServiceProvider.GetRequiredService<IDeviceInformation>()
        };

        response.WriteBody(responseBody, resolvedVersion);
    }
}