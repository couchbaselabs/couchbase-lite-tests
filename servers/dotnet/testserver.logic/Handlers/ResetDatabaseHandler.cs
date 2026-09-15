using System.Net;
using System.Text.Json;
using JetBrains.Annotations;
using TestServer.Utilities;

namespace TestServer.Handlers;

internal static partial class HandlerList
{
    [HttpHandler("reset")]
    [UsedImplicitly]
    public static async Task ResetDatabaseHandler(Session session, JsonDocument body, HttpListenerResponse response)
    {
        if(body.RootElement.TryGetProperty("test", out var name) && name.ValueKind == JsonValueKind.String) {
            Serilog.Log.Logger.Information(">>>>>>>>>> {name}", name);
        }

        if(!body.RootElement.TryGetProperty("databases", out var databases) || databases.ValueKind != JsonValueKind.Object) {
            await response.WriteEmptyBody().ConfigureAwait(false);
            return;
        }

        // I want to coalesce these so the unzip operation only happens once per dataset
        var datasetToDbNames = new Dictionary<string, List<string>>();
        foreach(var newDatabase in databases.EnumerateObject()) {
            var dbName = newDatabase.Name;
            if(newDatabase.Value.ValueKind != JsonValueKind.Object) {
                await response.WriteBody($"Invalid value for database '{dbName}'", HttpStatusCode.BadRequest).ConfigureAwait(false);
                return;
            }

            if(newDatabase.Value.TryGetProperty("collections", out var collectionsJson)) {
                // collections were specified, dataset is disallowed
                if(newDatabase.Value.TryGetProperty("dataset", out var _)) {
                    await response.WriteBody($"Database '{dbName}' specified both collections and dataset, this is invalid!", HttpStatusCode.BadRequest).ConfigureAwait(false);
                    return;
                }

                // collections must be an array
                if(collectionsJson.ValueKind != JsonValueKind.Array) {
                    await response.WriteBody($"Database '{dbName}' has invalid collections specified (not array)", HttpStatusCode.BadRequest).ConfigureAwait(false);
                    return;
                }

                // The collections array must only contain strings
                if(collectionsJson.EnumerateArray().Any(x => x.ValueKind != JsonValueKind.String)) {
                    await response.WriteBody($"Database '{dbName}' has invalid collections specified (non-string entry found)", HttpStatusCode.BadRequest).ConfigureAwait(false);
                    return;
                }
            } else if(newDatabase.Value.TryGetProperty("dataset", out var datasetJson)) {
                // dataset was specified, collections is disallowed
                if (newDatabase.Value.TryGetProperty("collections", out var _)) {
                    await response.WriteBody($"Database '{dbName}' specified both collections and dataset, this is invalid!", HttpStatusCode.BadRequest).ConfigureAwait(false);
                    return;
                }

                // dataset must be a string
                var datasetName = datasetJson.GetString();
                if (datasetName == null) {
                    await response.WriteBody($"Database '{dbName}' has invalid dataset specified (not string)", HttpStatusCode.BadRequest).ConfigureAwait(false);
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
        session.ObjectManager.Reset();
        // ReSharper disable once ForeachCanBeConvertedToQueryUsingAnotherGetEnumerator
        foreach(var newDatabase in databases.EnumerateObject()) {
            var dbName = newDatabase.Name;
            if (!newDatabase.Value.TryGetProperty("dataset", out _))
            {
                // Entries with dataset will be handled later via the coalesced dictionary
                tasks.Add(newDatabase.Value.TryGetProperty("collections", out var collectionsJson)
                    ? session.ObjectManager.LoadDatabase(null, [dbName],
                        collectionsJson.Deserialize<IReadOnlyList<string>>())
                    : session.ObjectManager.LoadDatabase(null, [dbName]));
            }
        }

        tasks.AddRange(datasetToDbNames.Select(datasetEntry 
            => session.ObjectManager.LoadDatabase(datasetEntry.Key, datasetEntry.Value)));

        try {
            await Task.WhenAll(tasks).WaitAsync(TimeSpan.FromSeconds(5)).ConfigureAwait(false);
        } catch(TimeoutException) {
            throw new ApplicationException("Timed out waiting for datasets to load");
        }

        await response.WriteEmptyBody().ConfigureAwait(false);
    }
}

