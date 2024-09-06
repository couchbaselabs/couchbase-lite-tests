using System;
using System.Collections.Generic;
using System.Linq;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading.Tasks;
using TestServer.Services;

namespace TestServer.Cli.Services
{
    internal sealed class CLIFileSystem : IFileSystem
    {
        public string AppDataDirectory => Path.GetDirectoryName(typeof(CLIFileSystem).Assembly.Location) ?? throw new ApplicationException("Bad app data directory");

        public Task<Stream> OpenAppPackageFileAsync(string path)
        {
            if (RuntimeInformation.IsOSPlatform(OSPlatform.Windows)) {
                path = path.Replace("/", "\\");
            }

            var actualPath = Path.Combine(AppDataDirectory, "Resources", path);
            return Task.FromResult<Stream>(File.OpenRead(actualPath));
        }
    }
}
