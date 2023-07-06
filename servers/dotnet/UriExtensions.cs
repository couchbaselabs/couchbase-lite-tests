using System.Collections.Specialized;
using System.Diagnostics.CodeAnalysis;

namespace TestServer
{
    internal static class UriExtensions
    {
        public static NameValueCollection ParseQueryString([NotNull] this Uri url)
        {
            var retVal = new NameValueCollection();
            if (String.IsNullOrEmpty(url.Query)) {
                return retVal;
            }

            foreach (var pair in url.Query.Substring(1).Split('&')) {
                var nameValue = pair.Split('=');
                retVal.Add(nameValue[0], nameValue[1]);
            }

            return retVal;
        }
    }
}
