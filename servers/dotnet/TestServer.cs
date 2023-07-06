using System.Diagnostics.Metrics;
using System.Net;

namespace TestServer
{
    public sealed class CBLTestServer
    {
        #region Constants

        private const ushort Port = 8080;

        private static readonly Stream NullStream = new MemoryStream(new byte[0]);

        public static readonly ObjectManager Manager = new ObjectManager(Path.Join(FileSystem.AppDataDirectory, "testfiles"));

        #endregion

        #region Variables

        private CancellationTokenSource? _cancelSource;
        private HttpListener? _httpListener;

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
                    Console.WriteLine("Weird error: null request, skipping...");
                    continue;
                }

                if (nextRequest.Request?.Url == null) {
                    Console.WriteLine("Weird error: null url, skipping...");
                    continue;
                }

                if (!IsValidMethod(nextRequest.Request)) {
                    nextRequest.Response.WriteEmptyBody(HttpStatusCode.MethodNotAllowed);
                    continue;
                }

                var _ = Router.Handle(nextRequest.Request.Url, nextRequest.Request.InputStream ?? NullStream, nextRequest.Response)
                    .ContinueWith(t => Console.Error.WriteLine($"Exception caught during router handling: {t.Exception?.InnerException}"),
                    TaskContinuationOptions.OnlyOnFaulted);
            }
        }

        #endregion
    }
}
