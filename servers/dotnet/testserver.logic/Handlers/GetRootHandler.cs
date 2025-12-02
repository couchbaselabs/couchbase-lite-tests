using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;
using System.Collections.Specialized;
using System.Net;
using System.Reflection;
using System.Text.Json;
using TestServer.Services;
using TestServer.Utilities;

namespace TestServer.Handlers;

internal static partial class HandlerList
{
    [HttpHandler("", noSession: true)]
    public static Task GetRootHandler(JsonDocument body, HttpListenerResponse response)
    {
        var responseBody = new
        {
            version = typeof(Couchbase.Lite.Database).Assembly.GetCustomAttribute<AssemblyInformationalVersionAttribute>()?.InformationalVersion,
            apiVersion = CBLTestServer.ApiVersion,
            cbl = "couchbase-lite-net",
            device = CBLTestServer.ServiceProvider.GetRequiredService<IDeviceInformation>()
        };

        response.WriteBody(responseBody);
        return Task.CompletedTask;
    }
}
