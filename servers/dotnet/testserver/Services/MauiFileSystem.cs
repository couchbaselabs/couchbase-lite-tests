namespace TestServer.Services
{
    internal sealed class MauiFileSystem : IFileSystem
    {
        public string AppDataDirectory => FileSystem.AppDataDirectory;

        public Task<Stream> OpenAppPackageFileAsync(string path) => FileSystem.OpenAppPackageFileAsync(path);
    }
}
