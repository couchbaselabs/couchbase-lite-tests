using Microsoft.Extensions.DependencyInjection;
using System.Net;
using System.Reflection;
using System.Text.Json;
using JetBrains.Annotations;
using TestServer.Services;

namespace TestServer.Handlers;

internal static partial class HandlerList
{
    [HttpHandler("", noSession: true)]
    [UsedImplicitly]
    public static async Task GetRootHandler(JsonDocument body, HttpListenerResponse response)
    {
        var responseBody = new
        {
            version = typeof(Couchbase.Lite.Database).Assembly.GetCustomAttribute<AssemblyInformationalVersionAttribute>()?.InformationalVersion,
            apiVersion = CBLTestServer.ApiVersion,
            cbl = "couchbase-lite-net",
            device = CBLTestServer.ServiceProvider.GetRequiredService<IDeviceInformation>()
        };

        await response.WriteBody(responseBody).ConfigureAwait(false);
    }
}
