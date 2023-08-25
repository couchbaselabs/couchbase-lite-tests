using Couchbase.Lite;
using System.Diagnostics;
using System.Diagnostics.CodeAnalysis;
using System.Net;
using System.Reflection;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization.Metadata;
using TestServer.Handlers;

using HandlerAction = System.Action<int,
    System.Text.Json.JsonDocument,
    System.Net.HttpListenerResponse>;

namespace TestServer.Handlers
{
    internal static partial class HandlerList
    {
#if !HEADLESS
        private static readonly IServiceProvider ServiceProvider = Application.Current!.MainPage!.Handler!.MauiContext!.Services;
#endif

        private static (string scope, string name) CollectionSpec(string inputName)
        {
            var split = inputName.Split('.');
            if(split.Length == 1) {
                throw new JsonException($"Invalid collection name (must be scope qualified): {inputName}");
            }

            return (split[0], split[1]);
        }

        private static bool TryDeserialize<T>(this JsonElement element, HttpListenerResponse response, int version, [NotNullWhen(true)]out T? result)
        {
            result = default;
            try {
                result = element.Deserialize<T>(new JsonSerializerOptions
                {
                    IncludeFields = true
                })!;
                return true;
            } catch (JsonException ex) {
                response.WriteBody(Router.CreateErrorResponse($"Invalid json received: {ex.Message}"), version, HttpStatusCode.BadRequest);
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

        public HttpHandlerAttribute(string path)
        {
            Path = path;
        }
    }

    public static class Router
    {
        #region Constants

        public const string ApiVersionHeader = "CBLTest-API-Version";

        private static readonly IDictionary<string, HandlerAction> RouteMap =
            new Dictionary<string, HandlerAction>();

        #endregion

        #region Constructors

        static Router()
        {
            foreach(var method in typeof(HandlerList).GetMethods()
                .Where(x => x.GetCustomAttribute(typeof(HttpHandlerAttribute)) != null)) {
                var key = method.GetCustomAttribute<HttpHandlerAttribute>()!.Path;
                var invocation = new HandlerAction((args, body, response) => method.Invoke(null, new object[] { args, body, response }));
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

        internal static void HandleException(Exception ex, Uri endpoint, int version, HttpListenerResponse response)
        {
            var msg = MultiExceptionString(ex);
            Debug.WriteLine($"Error in handler for {endpoint}");
            Debug.WriteLine(msg);
            Console.WriteLine($"Error in handler for {endpoint}");
            Console.WriteLine(msg);
            response.WriteBody(CreateErrorResponse(msg), version, HttpStatusCode.InternalServerError);
        }

        internal static async Task Handle(Uri endpoint, Stream body, HttpListenerResponse response, int version)
        {
            if(version > CBLTestServer.MaxApiVersion) {
                response.WriteBody("The API version specified is not supported", CBLTestServer.MaxApiVersion, HttpStatusCode.Forbidden);
                return;
            }

            var path = endpoint.AbsolutePath!.TrimStart('/');
            if (version == 0 && path != "") {
                response.WriteBody($"{ApiVersionHeader} missing or set to 0 on a versioned endpoint", CBLTestServer.MaxApiVersion, HttpStatusCode.Forbidden);
                return;
            }

            if (!RouteMap.TryGetValue(path, out HandlerAction? action)) {
                response.WriteEmptyBody(version, HttpStatusCode.NotFound);
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
                Debug.WriteLine($"Error deserializing POST body for {endpoint}");
                Debug.WriteLine(msg);
                Console.WriteLine($"Error deserializing POST body for {endpoint}");
                Console.WriteLine(msg);
                var topEx = new ApplicationException($"Error deserializing POST body for {endpoint}", ex);
                response.WriteBody(CreateErrorResponse(topEx), version, HttpStatusCode.BadRequest);
                return;
            }

            try {
                action(version, bodyObj, response);
            } catch (TargetInvocationException ex) {
                switch(ex.InnerException) {
                    case null:
                        HandleException(ex, endpoint, version, response);
                        break;
                    case JsonException e:
                        response.WriteBody(CreateErrorResponse(e.Message), version, HttpStatusCode.BadRequest);
                        break;
                    default:
                        HandleException(ex.InnerException, endpoint, version, response);
                        break;
                }
            } catch (Exception ex) {
                HandleException(ex, endpoint, version, response);
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