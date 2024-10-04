using Microsoft.Extensions.DependencyInjection;
using System.Net;
using System.Reflection;
using TestServer.Services;

namespace TestServer
{
    public sealed class CBLTestServer
    {
        #region Constants

        public static readonly int MaxApiVersion = 1;

        public static readonly string ServerID = Guid.NewGuid().ToString();

        private const ushort DefaultPort = 8080;

        private static readonly Stream NullStream = new MemoryStream(Array.Empty<byte>());

        private static IServiceProvider _ServiceProvider = default!;

        public static ObjectManager Manager { get; private set; } = default!;

        #endregion

        public ushort Port { get; set; } = DefaultPort;

        #region Variables

        private CancellationTokenSource? _cancelSource;
        private HttpListener? _httpListener;

        #endregion

        public static string Version => typeof(CBLTestServer).Assembly.GetCustomAttribute<AssemblyFileVersionAttribute>()!.Version;

        public static IServiceProvider ServiceProvider
        {
            get => _ServiceProvider;
            set {
                _ServiceProvider = value;
                var fileSystem = _ServiceProvider.GetRequiredService<IFileSystem>();
                Manager = new ObjectManager(Path.Join(fileSystem.AppDataDirectory, "testfiles"));
            }
        }

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
                    Serilog.Log.Logger.Warning("Weird error: null request, skipping...");
                    continue;
                }

                if (nextRequest.Request?.Url == null) {
                    Serilog.Log.Logger.Warning("Weird error: null url, skipping...");
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
                    .ContinueWith(t => Serilog.Log.Logger.Warning("Exception caught during router handling: {e}", t.Exception?.InnerException),
                    TaskContinuationOptions.OnlyOnFaulted);
            }
        }

        #endregion
    }
}
