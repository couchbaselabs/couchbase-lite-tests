using Couchbase.Lite;
using System;
using System.Collections.Generic;
using System.Linq;
using System.Net;
using System.Text;
using System.Text.Json;
using System.Threading.Tasks;
using TestServer.Utilities;

namespace TestServer.Handlers
{
    internal static partial class HandlerList
    {

        [HttpHandler("performMaintenance")]
        public static Task PerformMaintenanceHandler(Session session, JsonDocument body, HttpListenerResponse response)
        {
            if (!body.RootElement.TryGetProperty("database", out var database) || database.ValueKind != JsonValueKind.String) {
                response.WriteBody(Router.CreateErrorResponse("'database' property not found or invalid"), HttpStatusCode.BadRequest);
                return Task.CompletedTask;
            }

            if (!body.RootElement.TryGetProperty("maintenanceType", out var maintenanceStr) || maintenanceStr.ValueKind != JsonValueKind.String) {
                response.WriteBody(Router.CreateErrorResponse("'maintenanceType' property not found or invalid"), HttpStatusCode.BadRequest);
                return Task.CompletedTask;
            }


            if (!Enum.TryParse<MaintenanceType>(maintenanceStr.GetString(), true, out var maintenanceType)) {
                response.WriteBody(Router.CreateErrorResponse($"'maintenanceType' value unknown: {maintenanceStr}"), HttpStatusCode.BadRequest);
                return Task.CompletedTask;
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

                response.WriteBody(errorObject, HttpStatusCode.BadRequest);
                return Task.CompletedTask;
            }

            dbObject.PerformMaintenance(maintenanceType);
            response.WriteEmptyBody();
            return Task.CompletedTask;
        }
    }
}
