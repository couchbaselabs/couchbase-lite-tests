using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using System.Threading.Tasks;

namespace TestServer.Services
{
    public interface IFileSystem
    {
        Task<Stream> OpenAppPackageFileAsync(string path);

        string AppDataDirectory { get; }
    }
}
