using System.Collections.Specialized;
using System.Net;
using System.Reflection;
using System.Text.Json;
using TestServer.Services;

namespace TestServer.Handlers;

internal static partial class HandlerList
{
    [HttpHandler("reset")]
    public static void ResetDatabaseHandler(NameValueCollection args, JsonDocument body, HttpListenerResponse response)
    {
        if(!body.RootElement.TryGetProperty("datasets", out var datasets) || datasets.ValueKind != JsonValueKind.Object) {
            response.WriteBody("Missing or invalid key 'datasets' in JSON body", HttpStatusCode.BadRequest);
            return;
        }

        foreach(var dataset in datasets.EnumerateObject()) {
            var datasetName = dataset.Name;
            if(dataset.Value.ValueKind != JsonValueKind.Array) {
                response.WriteBody($"Invalid value for dataset '{datasetName}'", HttpStatusCode.BadRequest);
                return;
            }

            if(dataset.Value.EnumerateArray().Any(x => x.ValueKind != JsonValueKind.String)) {
                response.WriteBody($"Invalid db name found inside of array for '{datasetName}'", HttpStatusCode.BadRequest);
                return;
            }
        }

        var tasks = new List<Task>();
        CBLTestServer.Manager.Reset();
        foreach(var dataset in datasets.EnumerateObject()) {
            var datasetName = dataset.Name;
            tasks.Add(CBLTestServer.Manager.LoadDataset(datasetName, dataset.Value.EnumerateArray().Select(x => x.GetString()!)));
        }

        if (!Task.WaitAll(tasks.ToArray(), TimeSpan.FromSeconds(5))) {
            throw new ApplicationException("Timed out waiting for datasets to load");
        }

        response.WriteEmptyBody();
    }
}

