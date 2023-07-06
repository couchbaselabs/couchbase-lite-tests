using System.Diagnostics;
using System.Net;
using System.Text;
using System.Text.Json;
using TestServer.Handlers;

using HandlerAction = System.Action<System.Collections.Specialized.NameValueCollection,
    System.Text.Json.JsonDocument,
    System.Net.HttpListenerResponse>;

namespace TestServer.Handlers
{
    internal static partial class HandlerList
    {
        private static readonly IServiceProvider ServiceProvider = Application.Current!.MainPage!.Handler!.MauiContext!.Services;

        private static (string scope, string name) CollectionSpec(string inputName)
        {
            var split = inputName.Split('.');
            if(split.Length == 1) {
                return ("_default", split[0]);
            }

            return (split[0], split[1]);
        }
    }
}

namespace TestServer
{
    public static class Router
    {
        #region Constants

        private static readonly IDictionary<string, HandlerAction> RouteMap =
            new Dictionary<string, HandlerAction>
            {
                [""] = HandlerList.GetRootHandler,
                ["reset"] = HandlerList.ResetDatabaseHandler,
                ["getAllDocumentIDs"] = HandlerList.AllDocumentIDsHandler
            };

        #endregion

        #region Public Methods

        public static object CreateErrorResponse(Exception ex)
        {
            return CreateErrorResponse(MultiExceptionString(ex));
        }

        public static object CreateErrorResponse(string message)
        {
            return new
            {
                domain = 0,
                code = 1,
                message = message
            };
        }

        #endregion

        #region Internal Methods

        internal static async Task Handle(Uri endpoint, Stream body, HttpListenerResponse response)
        {
            if (!RouteMap.TryGetValue(endpoint.AbsolutePath!.TrimStart('/'), out HandlerAction? action)) {
                response.WriteEmptyBody(HttpStatusCode.NotFound);
                return;
            }

            JsonDocument bodyObj;
            try {
                if (action != HandlerList.GetRootHandler) {
                    bodyObj = await JsonDocument.ParseAsync(body);
                } else {
                    bodyObj = JsonDocument.Parse("null");
                }
            } catch (Exception ex) {
                var msg = MultiExceptionString(ex);
                Debug.WriteLine($"Error deserializing POST body for {endpoint}");
                Debug.WriteLine(msg);
                Console.WriteLine($"Error deserializing POST body for {endpoint}");
                Console.WriteLine(msg);
                var topEx = new ApplicationException($"Error deserializing POST body for {endpoint}", ex);
                response.WriteBody(CreateErrorResponse(topEx), HttpStatusCode.BadRequest);
                return;
            }

            var args = endpoint.ParseQueryString();
            try {
                action(args, bodyObj, response);
            } catch (Exception ex) {
                var msg = MultiExceptionString(ex);
                Debug.WriteLine($"Error in handler for {endpoint}");
                Debug.WriteLine(msg);
                Console.WriteLine($"Error in handler for {endpoint}");
                Console.WriteLine(msg);
                response.WriteBody(CreateErrorResponse(msg), HttpStatusCode.InternalServerError);
            }
        }

        #endregion

        #region Private Methods

        private static string MultiExceptionString(Exception ex, StringBuilder? existingSb = null, string indent = "")
        {
            StringBuilder sb = existingSb ?? new StringBuilder();
            if (ex is AggregateException ae) {
                sb.AppendLine("Aggregated:");
                foreach (var inner in ae.InnerExceptions) {
                    MultiExceptionString(inner, sb, indent + "\t");
                }
            } else {
                sb.Append(indent);
                sb.AppendLine($"{ex.GetType().FullName}: {ex.Message}");

                if (ex.InnerException != null) {
                    MultiExceptionString(ex.InnerException, sb, indent + "\t");
                }
            }

            return sb.ToString();
        }

        #endregion
    }
}