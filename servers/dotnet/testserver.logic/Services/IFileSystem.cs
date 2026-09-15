namespace TestServer.Services
{
    public interface IFileSystem
    {
        Task<Stream> OpenAppPackageFileAsync(string path);

        string AppDataDirectory { get; }
    }
}
