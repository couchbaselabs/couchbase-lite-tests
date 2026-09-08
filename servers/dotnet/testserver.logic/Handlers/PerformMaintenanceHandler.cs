using Couchbase.Lite;
using System.Net;
using System.Text.Json;
using JetBrains.Annotations;
using TestServer.Utilities;

namespace TestServer.Handlers
{
    internal static partial class HandlerList
    {

        [HttpHandler("performMaintenance")]
        [UsedImplicitly]
        public static async Task PerformMaintenanceHandler(Session session, JsonDocument body, HttpListenerResponse response)
        {
            if (!body.RootElement.TryGetProperty("database", out var database) || database.ValueKind != JsonValueKind.String) {
                await response.WriteBody(Router.CreateErrorResponse("'database' property not found or invalid"), HttpStatusCode.BadRequest).ConfigureAwait(false);
                return;
            }

            if (!body.RootElement.TryGetProperty("maintenanceType", out var maintenanceStr) || maintenanceStr.ValueKind != JsonValueKind.String) {
                await response.WriteBody(Router.CreateErrorResponse("'maintenanceType' property not found or invalid"), HttpStatusCode.BadRequest).ConfigureAwait(false);
                return;
            }


            if (!Enum.TryParse<MaintenanceType>(maintenanceStr.GetString(), true, out var maintenanceType)) {
                await response.WriteBody(Router.CreateErrorResponse($"'maintenanceType' value unknown: {maintenanceStr}"), HttpStatusCode.BadRequest).ConfigureAwait(false);
                return;
            }

            var dbName = database.GetString()!;
            var dbObject = session.ObjectManager.GetDatabase(dbName);
            if (dbObject == null) {
                var errorObject = new
                {
                    domain = (int)CouchbaseLiteErrorType.CouchbaseLite + 1,
                    code = (int)CouchbaseLiteError.NotFound,
                    message = $"database '{dbName}' not registered!"
                };

                await response.WriteBody(errorObject, HttpStatusCode.BadRequest).ConfigureAwait(false);
                return;
            }

            dbObject.PerformMaintenance(maintenanceType);
            await response.WriteEmptyBody().ConfigureAwait(false);
        }
    }
}
