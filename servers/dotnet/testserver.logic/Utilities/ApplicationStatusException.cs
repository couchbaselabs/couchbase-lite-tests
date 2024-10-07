using System;
using System.Collections.Generic;
using System.Linq;
using System.Net;
using System.Text;
using System.Threading.Tasks;

namespace TestServer.Utilities
{
    internal class ApplicationStatusException : Exception
    {
        public HttpStatusCode StatusCode { get; }

        public ApplicationStatusException(string message, HttpStatusCode status)
            : base(message)
        {
            StatusCode = status;
        }
    }

    internal class BadRequestException : ApplicationStatusException
    {
        public BadRequestException(string message)
            : base(message, HttpStatusCode.BadRequest)
        {

        }
    }
}
