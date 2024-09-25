using System.Net;
using System.Text.Json;

namespace TestServer.Handlers;

internal static partial class HandlerList
{
    [HttpHandler("reset")]
    public static async Task ResetDatabaseHandler(int version, JsonDocument body, HttpListenerResponse response)
    {
        if(body.RootElement.TryGetProperty("test", out var name) && name.ValueKind == JsonValueKind.String) {
            Serilog.Log.Logger.Information(">>>>>>>>>> {name}", name);
        }
        
        if(!body.RootElement.TryGetProperty("databases", out var databases) || databases.ValueKind != JsonValueKind.Object) {
            response.WriteEmptyBody(version);
            return;
        }

        // I want to coalesce these so the unzip only happens once per dataset
        var datasetToDbNames = new Dictionary<string, List<string>>();
        foreach(var newDatabase in databases.EnumerateObject()) {
            var dbName = newDatabase.Name;
            if(newDatabase.Value.ValueKind != JsonValueKind.Object) {
                response.WriteBody($"Invalid value for database '{dbName}'", version, HttpStatusCode.BadRequest);
                return;
            }

            if(newDatabase.Value.TryGetProperty("collections", out var collectionsJson)) {
                // collections was specified, dataset is disallowed
                if(newDatabase.Value.TryGetProperty("dataset", out var _)) {
                    response.WriteBody($"Database '{dbName}' specified both collections and dataset, this is invalid!", 
                        version, HttpStatusCode.BadRequest);
                    return;
                }

                // collections must be an array
                if(collectionsJson.ValueKind != JsonValueKind.Array) {
                    response.WriteBody($"Database '{dbName}' has invalid collections specified (not array)", 
                        version, HttpStatusCode.BadRequest);
                    return;
                }

                // The collections array must only contain strings
                if(collectionsJson.EnumerateArray().Any(x => x.ValueKind != JsonValueKind.String)) {
                    response.WriteBody($"Database '{dbName}' has invalid collections specified (non-string entry found)",
                        version, HttpStatusCode.BadRequest);
                    return;
                }
            } else if(newDatabase.Value.TryGetProperty("dataset", out var datasetJson)) {
                // dataset was specified, collections is disallowed
                if (newDatabase.Value.TryGetProperty("collections", out var _)) {
                    response.WriteBody($"Database '{dbName}' specified both collections and dataset, this is invalid!",
                        version, HttpStatusCode.BadRequest);
                    return;
                }

                // dataset must be a string
                var datasetName = datasetJson.GetString();
                if (datasetName == null) {
                    response.WriteBody($"Database '{dbName}' has invalid dataset specified (not string)",
                        version, HttpStatusCode.BadRequest);
                    return;
                }

                // Coalesce for later
                if(!datasetToDbNames.TryGetValue(datasetName, out var createDbNames)) {
                    createDbNames = new List<string>();
                    datasetToDbNames[datasetName] = createDbNames;
                }

                createDbNames.Add(dbName);
            }
        }

        var tasks = new List<Task>();
        CBLTestServer.Manager.Reset();
        foreach(var newDatabase in databases.EnumerateObject()) {
            var dbName = newDatabase.Name;
            if (!newDatabase.Value.TryGetProperty("dataset", out var _)) {
                // Entries with dataset will be handled later via the coalesced dictionary
                if(newDatabase.Value.TryGetProperty("collections", out var collectionsJson)) {
                    tasks.Add(CBLTestServer.Manager.LoadDatabase(null, [dbName], collectionsJson.Deserialize<IEnumerable<string>>()));
                } else {
                    tasks.Add(CBLTestServer.Manager.LoadDatabase(null, [dbName], null));
                }
            }
        }

        foreach(var datasetEntry in datasetToDbNames) {
            tasks.Add(CBLTestServer.Manager.LoadDatabase(datasetEntry.Key, datasetEntry.Value));
        }

        try {
            await Task.WhenAll(tasks).WaitAsync(TimeSpan.FromSeconds(5)).ConfigureAwait(false);
        } catch(TimeoutException) {
            throw new ApplicationException("Timed out waiting for datasets to load");
        }

        response.WriteEmptyBody(version);
    }
}

