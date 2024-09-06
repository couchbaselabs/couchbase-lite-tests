using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using System.Threading.Tasks;

namespace TestServer.Services
{
    internal sealed class MauiFileSystem : IFileSystem
    {
        public string AppDataDirectory => FileSystem.AppDataDirectory;

        public Task<Stream> OpenAppPackageFileAsync(string path) => FileSystem.OpenAppPackageFileAsync(path);
    }
}
