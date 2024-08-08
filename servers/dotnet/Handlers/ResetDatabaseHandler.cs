using Microsoft.Extensions.Logging;
using System.Collections.Specialized;
using System.Net;
using System.Reflection;
using System.Text.Json;
using TestServer.Services;

namespace TestServer.Handlers;

internal static partial class HandlerList
{
    private static readonly ILogger ResetLogger =
        MauiProgram.ServiceProvider.GetRequiredService<ILoggerFactory>().CreateLogger("ResetHandler");

    [HttpHandler("reset")]
    public static async Task ResetDatabaseHandler(int version, JsonDocument body, HttpListenerResponse response)
    {
        if(body.RootElement.TryGetProperty("name", out var name) && name.ValueKind == JsonValueKind.String) {
            ResetLogger.LogInformation(">>>>>>>>>> {name}", name);
        }
        
        if(!body.RootElement.TryGetProperty("datasets", out var datasets) || datasets.ValueKind != JsonValueKind.Object) {
            response.WriteEmptyBody(version);
            return;
        }

        foreach(var dataset in datasets.EnumerateObject()) {
            var datasetName = dataset.Name;
            if(dataset.Value.ValueKind != JsonValueKind.Array) {
                response.WriteBody($"Invalid value for dataset '{datasetName}'", version, HttpStatusCode.BadRequest);
                return;
            }

            if(dataset.Value.EnumerateArray().Any(x => x.ValueKind != JsonValueKind.String)) {
                response.WriteBody($"Invalid db name found inside of array for '{datasetName}'", version, HttpStatusCode.BadRequest);
                return;
            }
        }

        var tasks = new List<Task>();
        CBLTestServer.Manager.Reset();
        foreach(var dataset in datasets.EnumerateObject()) {
            var datasetName = dataset.Name;
            tasks.Add(CBLTestServer.Manager.LoadDataset(datasetName, dataset.Value.EnumerateArray().Select(x => x.GetString()!)));
        }

        try {
            await Task.WhenAll(tasks).WaitAsync(TimeSpan.FromSeconds(5)).ConfigureAwait(false);
        } catch(TimeoutException) {
            throw new ApplicationException("Timed out waiting for datasets to load");
        }

        response.WriteEmptyBody(version);
    }
}

