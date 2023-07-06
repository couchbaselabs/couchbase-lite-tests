using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Linq;
using System.Net;
using System.Text;
using System.Text.Json;
using System.Threading.Tasks;

namespace TestServer
{
    internal static class HttpListenerResponseExtensions
    {
        public static void WriteBody<T>(this HttpListenerResponse response, T bodyObj, HttpStatusCode status = HttpStatusCode.OK)
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
                response.OutputStream.Write(body, 0, body.Length);
                response.Close();
            } catch (ObjectDisposedException) {
                // Swallow...other side closed the connection
            }
        }

        public static void WriteRawBody(this HttpListenerResponse response, string bodyStr, HttpStatusCode status = HttpStatusCode.OK)
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
                response.OutputStream.Write(body, 0, body.Length);
                response.Close();
            } catch (ObjectDisposedException) {
                // Swallow...other side closed the connection
            }
        }

        public static void WriteEmptyBody([NotNull] this HttpListenerResponse response, HttpStatusCode code = HttpStatusCode.OK)
        {
            try {
                var body = Encoding.UTF8.GetBytes("{}");
                response.ContentLength64 = body.LongLength;
                response.ContentEncoding = Encoding.UTF8;
                response.StatusCode = (int)code;
                response.OutputStream.Write(body, 0, body.Length);
                response.Close();
            } catch (ObjectDisposedException) {
                // Swallow...other side closed the connection
            }
        }
    }
}
