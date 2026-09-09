using System.Net;
using System.Text;
using System.Text.Json;
using TestServer.Utilities;

namespace TestServer
{
    internal static class HttpListenerResponseExtensions
    {
        private static readonly JsonSerializerOptions Options = new JsonSerializerOptions();

        static HttpListenerResponseExtensions()
        {
            Options.Converters.Add(new BlobConverter());
        }

        extension(HttpListenerResponse response)
        {
            private void AddHeaders()
            {
                response.AddHeader("CBLTest-API-Version", CBLTestServer.ApiVersion.ToString());
                response.AddHeader("CBLTest-Server-ID", CBLTestServer.ServerID);
            }

            public async Task WriteBody<T>(T bodyObj, HttpStatusCode status = HttpStatusCode.OK)
            {
                if (response.OutputStream == null) {
                    throw new InvalidOperationException("Cannot write to a response with a null OutputStream");
                }

                try {
                    response.ContentType = "application/json";
                    response.ContentEncoding = Encoding.UTF8;
                    response.StatusCode = (int)status;
                    response.AddHeaders();
                    await JsonSerializer.SerializeAsync(response.OutputStream, bodyObj, Options).ConfigureAwait(false);
                    response.Close();
                } catch (ObjectDisposedException) {
                    // Swallow...other side closed the connection
                }
            }

            public async Task WriteEmptyBody(HttpStatusCode code = HttpStatusCode.OK)
            {
                try {
                    var body = "{}"u8.ToArray();
                    response.ContentType = "application/json";
                    response.ContentLength64 = body.LongLength;
                    response.ContentEncoding = Encoding.UTF8;
                    response.StatusCode = (int)code;
                    response.AddHeaders();
                    await response.OutputStream.WriteAsync(body).ConfigureAwait(false);
                    response.Close();
                } catch (ObjectDisposedException) {
                    // Swallow...other side closed the connection
                }
            }
        }
    }
}
