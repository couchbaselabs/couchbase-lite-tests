using System.Net;

namespace TestServer.Utilities
{
    internal class ApplicationStatusException(string message, HttpStatusCode status) : Exception(message)
    {
        public HttpStatusCode StatusCode { get; } = status;
    }

    internal class BadRequestException(string message) : ApplicationStatusException(message, HttpStatusCode.BadRequest);
}
