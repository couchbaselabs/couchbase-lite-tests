using Couchbase.Lite;
using Couchbase.Lite.Logging;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;
using System.Diagnostics;
using System.Diagnostics.CodeAnalysis;
using System.Net;
using System.Reflection;
using System.Text;
using System.Text.Json;
using TestServer.Handlers;
using TestServer.Utilities;

// This is a shim between the received HTTP message
// and the actual invocation which will transform
// the clientID into a session IF NEEDED
using HandlerAction = System.Func<System.String?,
    System.Text.Json.JsonDocument,
    System.Net.HttpListenerResponse,
    System.Threading.Tasks.Task>;

namespace TestServer.Handlers
{
    internal static partial class HandlerList
    {
        public static (string scope, string name) CollectionSpec(string inputName)
        {
            var split = inputName.Split('.');
            if(split.Length == 1) {
                throw new JsonException($"Invalid collection name (must be scope qualified): {inputName}");
            }

            return (split[0], split[1]);
        }

        private static bool TryDeserialize<T>(this JsonElement element, HttpListenerResponse response, [NotNullWhen(true)]out T? result)
        {
            result = default;
            try {
                result = element.Deserialize<T>(new JsonSerializerOptions
                {
                    IncludeFields = true
                })!;
                return true;
            } catch (JsonException ex) {
                response.WriteBody(Router.CreateErrorResponse($"Invalid json received: {ex.Message}"), HttpStatusCode.BadRequest);
            }

            return false;
        }

        private static IEnumerable<T> NotNull<T>(this IEnumerable<T?>? input) where T : class
        {
            if(input == null) {
                return Enumerable.Empty<T>();
            }

            return input.Where(x => x != null).Select(x => x!);
        }
    }
}

namespace TestServer
{
    public static class TestServerErrorDomain
    {
        public static readonly string TestServer = "TestServer";
        public static readonly string CouchbaseLite = "CBL";
        public static readonly string POSIX = "POSIX";
        public static readonly string SQLite = "SQLite";
        public static readonly string Fleece = "Fleece";
    }

    [AttributeUsage(AttributeTargets.Method)]
    internal sealed class HttpHandlerAttribute : Attribute
    {
        public string Path { get; }

        public bool NoSession { get; }

        public HttpHandlerAttribute(string path, bool noSession = false)
        {
            Path = path;
            NoSession = noSession;
        }
    }

    public static class Router
    {
        #region Constants

        public const string ApiVersionHeader = "CBLTest-API-Version";
        public const string ClientIdHeader = "CBLTest-Client-ID";

        private static readonly Dictionary<string, HandlerAction> RouteMap =
            new();

        #endregion

        #region Constructors

        private static IEnumerable<(string, MethodInfo)> HandlerMethods(bool noSession)
        {
            return typeof(HandlerList).GetMethods().Where(x =>
            {
                var att = x.GetCustomAttribute<HttpHandlerAttribute>();
                if (att == null) {
                    return false;
                }

                return att.NoSession == noSession;
            }).Select(x => (x.GetCustomAttribute<HttpHandlerAttribute>()!.Path, x));
        }

        static Router()
        {
            foreach(var (key, method) in HandlerMethods(false)) {
                var invocation = new HandlerAction((clientId, body, response) => (Task)method.Invoke(null, [Session.For(clientId), body, response])!);
                RouteMap.Add(key, invocation);
            }

            foreach (var (key, method) in HandlerMethods(true)) {
                var invocation = new HandlerAction((clientId, body, response) => (Task)method.Invoke(null, [body, response])!);
                RouteMap.Add(key, invocation);
            }
        }

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

        public static (string domain, int code) MapError(CouchbaseException ex)
        {
            switch(ex.Domain) {
                case CouchbaseLiteErrorType.POSIX:
                    return (TestServerErrorDomain.POSIX, ex.Error);
                case CouchbaseLiteErrorType.SQLite:
                    return (TestServerErrorDomain.SQLite, ex.Error);
                case CouchbaseLiteErrorType.Fleece:
                    return (TestServerErrorDomain.Fleece, ex.Error);
                default: {
                    return (TestServerErrorDomain.CouchbaseLite, ex.Error);
                }
            }
        }

        #endregion

        #region Internal Methods

        internal static void HandleException(Exception ex, Uri endpoint, HttpListenerResponse response)
        {
            if(ex is JsonException) {
                response.WriteBody(CreateErrorResponse(ex.Message), HttpStatusCode.BadRequest);
                return;
            }

            if(ex is ApplicationStatusException e) {
                response.WriteBody(CreateErrorResponse(ex.Message), e.StatusCode);
                return;
            }

            var msg = MultiExceptionString(ex);
            Serilog.Log.Logger.Warning("Error in handler for {endpoint}", endpoint);
            Serilog.Log.Logger.Warning("{msg}", msg);
            response.WriteBody(CreateErrorResponse(msg), HttpStatusCode.InternalServerError);
        }

        internal static async Task Handle(string? clientId, Uri endpoint, Stream body, HttpListenerResponse response, int version)
        {
            var path = endpoint.AbsolutePath!.TrimStart('/');
            if (path != "") {
                if (version == 0) {
                    response.WriteBody($"{ApiVersionHeader} missing or set to 0 on a versioned endpoint",
                        HttpStatusCode.Forbidden);
                    return;
                }

                if(version != CBLTestServer.ApiVersion) {
                    response.WriteBody("The API version specified does not match this server", HttpStatusCode.Forbidden);
                    return;
                }
            }

            if (!RouteMap.TryGetValue(path, out var action)) {
                response.WriteEmptyBody(HttpStatusCode.NotFound);
                return;
            }

            JsonDocument bodyObj;
            try {
                if (path != "") {
                    bodyObj = await JsonDocument.ParseAsync(body);
                } else {
                    bodyObj = JsonDocument.Parse("null");
                }
            } catch (Exception ex) {
                var msg = MultiExceptionString(ex);
                Serilog.Log.Logger.Error("Error deserializing POST body for {endpoint}", endpoint);
                Serilog.Log.Logger.Error("{msg}", msg);
                var topEx = new ApplicationException($"Error deserializing POST body for {endpoint}", ex);
                response.WriteBody(CreateErrorResponse(topEx), HttpStatusCode.BadRequest);
                return;
            }

            try {
                await action(clientId, bodyObj, response).ConfigureAwait(false);
            } catch (TargetInvocationException ex) {
                switch(ex.InnerException) {
                    case null:
                        HandleException(ex, endpoint, response);
                        break;
                    default:
                        HandleException(ex.InnerException, endpoint, response);
                        break;
                }
            } catch (Exception ex) {
                HandleException(ex, endpoint, response);
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
