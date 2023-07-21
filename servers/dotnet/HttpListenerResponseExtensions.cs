using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Dynamic;
using System.Linq;
using System.Net;
using System.Text;
using System.Text.Json;
using System.Threading.Tasks;

namespace TestServer
{
    internal static class HttpListenerResponseExtensions
    {
        public static void AddHeaders(this HttpListenerResponse response, int version)
        {
            response.AddHeader("CBLTest-API-Version", version.ToString());
            response.AddHeader("CBLTest-Server-ID", CBLTestServer.ServerID);
        }

        public static void WriteBody<T>(this HttpListenerResponse response, T bodyObj, int version, HttpStatusCode status = HttpStatusCode.OK)
        {
            if (response.OutputStream == null) {
                throw new InvalidOperationException("Cannot write to a response with a null OutputStream");
            }
            
            var body = JsonSerializer.SerializeToUtf8Bytes(bodyObj);
            try {
                response.ContentType = "application/json";
                response.ContentLength64 = body.LongLength;
                response.ContentEncoding = Encoding.UTF8;
                response.StatusCode = (int)status;
                response.AddHeaders(version);
                response.OutputStream.Write(body, 0, body.Length);
                response.Close();
            } catch (ObjectDisposedException) {
                // Swallow...other side closed the connection
            }
        }

        public static void WriteRawBody(this HttpListenerResponse response, string bodyStr, int version, HttpStatusCode status = HttpStatusCode.OK)
        {
            if (response.OutputStream == null) {
                throw new InvalidOperationException("Cannot write to a response with a null OutputStream");
            }

            var body = Encoding.UTF8.GetBytes(bodyStr);
            try {
                response.ContentType = "application/json";
                response.ContentLength64 = body.LongLength;
                response.ContentEncoding = Encoding.UTF8;
                response.StatusCode = (int)status;
                response.AddHeaders(version);
                response.OutputStream.Write(body, 0, body.Length);
                response.Close();
            } catch (ObjectDisposedException) {
                // Swallow...other side closed the connection
            }
        }

        public static void WriteEmptyBody([NotNull] this HttpListenerResponse response, int version, HttpStatusCode code = HttpStatusCode.OK)
        {
            try {
                var body = Encoding.UTF8.GetBytes("{}");
                response.ContentType = "application/json";
                response.ContentLength64 = body.LongLength;
                response.ContentEncoding = Encoding.UTF8;
                response.StatusCode = (int)code;
                response.AddHeaders(version);
                response.OutputStream.Write(body, 0, body.Length);
                response.Close();
            } catch (ObjectDisposedException) {
                // Swallow...other side closed the connection
            }
        }
    }
}
