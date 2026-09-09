using System.Net;
using System.Reflection;

namespace TestServer
{
    public sealed class CBLTestServer
    {
        public static readonly int ApiVersion = 2;
        public static readonly string ServerID = Guid.NewGuid().ToString();
        private const ushort DEFAULT_PORT = 8080;
        
        private CancellationTokenSource? _cancelSource;
        private HttpListener? _httpListener;

        public ushort Port { get; init; } = DEFAULT_PORT;

        public static string Version => typeof(CBLTestServer).Assembly.GetCustomAttribute<AssemblyFileVersionAttribute>()!.Version;

        public static IServiceProvider ServiceProvider { get; set; } = null!;

        public Task Start()
        {
            Interlocked.Exchange(ref _httpListener, new HttpListener())?.Stop();
            Interlocked.Exchange(ref _cancelSource, new CancellationTokenSource())?.Cancel();

            _httpListener.Prefixes.Add($"http://*:{Port}/");
            _httpListener.Start();
            return Run();
        }

        public void Stop()
        {
            Interlocked.Exchange(ref _httpListener, null)?.Stop();
            Interlocked.Exchange(ref _cancelSource, null)?.Cancel();
        }

        private static bool IsValidMethod(HttpListenerRequest request)
        {
            if(request.Url?.AbsolutePath == "/") {
                return request.HttpMethod == "GET";
            }

            return request.HttpMethod == "POST";
        }

        private async Task Run()
        {
            var cancelSource = _cancelSource;
            var httpListener = _httpListener;
            if (cancelSource == null || httpListener == null) {
                return;
            }

            while (!cancelSource.IsCancellationRequested) {
                var nextRequest = await httpListener.GetContextAsync().ConfigureAwait(false);
                if (nextRequest.Request.Url == null) {
                    Serilog.Log.Logger.Warning("Weird error: null url, skipping...");
                    continue;
                }

                if (!IsValidMethod(nextRequest.Request)) {
                    _ = nextRequest.Response.WriteEmptyBody(HttpStatusCode.MethodNotAllowed).ConfigureAwait(false);
                    continue;
                }

                var version = 0;
                var versionHeader = nextRequest.Request.Headers.Get(Router.ApiVersionHeader);
                if(versionHeader != null) {
                    Int32.TryParse(versionHeader, out version);
                }

                var clientId = nextRequest.Request.Headers.Get(Router.ClientIdHeader);
                _ = Router.Handle(clientId, nextRequest.Request.Url, nextRequest.Request.InputStream, nextRequest.Response, version)
                    .ContinueWith(t => Serilog.Log.Logger.Warning("Exception caught during router handling: {e}", t.Exception?.InnerException),
                    TaskContinuationOptions.OnlyOnFaulted);
            }
        }
    }
}
