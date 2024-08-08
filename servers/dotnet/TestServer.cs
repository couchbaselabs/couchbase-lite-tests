using Couchbase.Lite.Logging;
using Microsoft.Extensions.Logging;
using System.Diagnostics.Metrics;
using System.Net;

namespace TestServer
{
    public sealed class CBLTestServer
    {
        #region Constants

        public static readonly int MaxApiVersion = 1;

        public static readonly string ServerID = Guid.NewGuid().ToString();

        private const ushort Port = 8080;

        private static readonly Stream NullStream = new MemoryStream(Array.Empty<byte>());

        public static readonly ObjectManager Manager = new ObjectManager(Path.Join(FileSystem.AppDataDirectory, "testfiles"));

        #endregion

        #region Variables

        private CancellationTokenSource? _cancelSource;
        private HttpListener? _httpListener;
        private readonly ILogger<CBLTestServer> _logger 
            = MauiProgram.ServiceProvider.GetRequiredService<ILoggerFactory>().CreateLogger<CBLTestServer>();

        #endregion

        #region Public Methods

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

        #endregion

        #region Private Methods

        private bool IsValidMethod(HttpListenerRequest request)
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
                if (nextRequest?.Request == null) {
                    _logger.LogWarning("Weird error: null request, skipping...");
                    continue;
                }

                if (nextRequest.Request?.Url == null) {
                    _logger.LogWarning("Weird error: null url, skipping...");
                    continue;
                }

                if (!IsValidMethod(nextRequest.Request)) {
                    nextRequest.Response.WriteEmptyBody(MaxApiVersion, HttpStatusCode.MethodNotAllowed);
                    continue;
                }

                var version = 0;
                var versionHeader = nextRequest.Request.Headers.Get(Router.ApiVersionHeader);
                if(versionHeader != null) {
                    int.TryParse(versionHeader, out version);
                }
                
                var _ = Router.Handle(nextRequest.Request.Url, nextRequest.Request.InputStream ?? NullStream, nextRequest.Response, version)
                    .ContinueWith(t => _logger.LogWarning("Exception caught during router handling: {e}", t.Exception?.InnerException),
                    TaskContinuationOptions.OnlyOnFaulted);
            }
        }

        #endregion
    }
}
