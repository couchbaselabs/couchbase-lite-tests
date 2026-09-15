using Couchbase.Lite;
using Nito.AsyncEx;
using System.IO.Compression;
using System.Net;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using TestServer.Handlers;

namespace TestServer
{
    public sealed class ObjectManager
    {
        private const string GITHUB_BASE_URL = "https://media.githubusercontent.com/media/couchbaselabs/couchbase-lite-tests/refs/heads/main/dataset/server/";

        private readonly Dictionary<string, Database> _activeDatabases = new();
        private readonly Dictionary<string, IDisposable> _activeDisposables = new();
        // ReSharper disable once CollectionNeverQueried.Local
        // Putting the object in the set is how to keep it from being GC
        private readonly HashSet<object> _keepAlives = [];
        private readonly AsyncReaderWriterLock _lock = new();
        private readonly HttpClient _httpClient = new();

        private readonly string _filesDirectory;

        public ObjectManager(string filesDirectory)
        {
            _filesDirectory = filesDirectory;
            Directory.CreateDirectory(_filesDirectory);
        }

        public void Reset()
        {
            using var l = _lock.WriterLock();

            foreach (var db in _activeDatabases) {
                try {
                    db.Value.Delete();
                    db.Value.Dispose();
                } catch (Exception ex) {
                    Serilog.Log.Logger.Warning(ex, "Failed to delete/dispose {name}", db.Value.Name);
                }
            }

            _activeDatabases.Clear();

            foreach (var d in _activeDisposables) {
                d.Value.Dispose();
            }

            _activeDisposables.Clear();


            _keepAlives.Clear();
        }

        public async Task LoadDatabase(string? datasetUrlString, IReadOnlyList<string> targetDbNames, IReadOnlyList<string>? collections = null)
        {
            Uri? datasetUrl = null;
            string? datasetName = null;
            if (datasetUrlString != null) {
                datasetUrl = new Uri(datasetUrlString);
                datasetName = datasetUrl.AbsolutePath.Split('/').Last().Split('.').First();
            }

            IEnumerable<string> targetsToCreate;
            using (_ = _lock.ReaderLock()) {
                targetsToCreate = targetDbNames.Where(x => !_activeDatabases.ContainsKey(x)).ToArray();
                if (!targetsToCreate.Any()) {
                    return;
                }
            }

            if(datasetUrl == null || datasetName == null) {
                CreateNewDatabases();
                return;
            }

            await using var asset = await DownloadIfNecessary(datasetUrl);
            if(asset == null) {
                throw new JsonException($"Request for nonexistent dataset '{datasetName}'");
            }
            var destinationZip = Path.Combine(_filesDirectory, $"{datasetName}.cblite2.zip");
            using var wl = _lock.WriterLock();
            if (File.Exists(destinationZip)) {
                File.Delete(destinationZip);
            }

            await using (var fout = File.OpenWrite(destinationZip)) {
                await asset.CopyToAsync(fout);
            }

            if (Database.Exists(datasetName, _filesDirectory)) {
                Database.Delete(datasetName, _filesDirectory);
            }

            ZipFile.ExtractToDirectory(destinationZip, _filesDirectory);
            CreateNewDatabases();
            Database.Delete(datasetName, _filesDirectory);
            return;

            void CreateNewDatabases()
            {
                foreach (var targetName in targetsToCreate) {
                    if (Database.Exists(targetName, _filesDirectory)) {
                        Database.Delete(targetName, _filesDirectory);
                    }

                    var dbConfig = new DatabaseConfiguration
                    {
                        Directory = _filesDirectory
                    };

                    if (datasetName != null) {
                        Database.Copy(Path.Join(_filesDirectory, $"{datasetName}.cblite2"), targetName, dbConfig);
                        _activeDatabases[targetName] = new Database(targetName, dbConfig);
                    } else {
                        var newDb = new Database(targetName, dbConfig);
                        _activeDatabases[targetName] = newDb;
                        if (collections == null) {
                            continue;
                        }

                        foreach (var collSpec in collections.Select(HandlerList.CollectionSpec))
                        {
                            using var coll = newDb.CreateCollection(collSpec.name, collSpec.scope);
                        }
                    }

                }
            }
        }

        public async Task<Stream> LoadBlob(string blobUrlString)
        {
            var retVal = await DownloadIfNecessary(new(blobUrlString)).ConfigureAwait(false);
            if (retVal != null) {
                return retVal;
            }

            var name = blobUrlString.Split('/').Last();
            throw new JsonException($"Request for nonexistent blob '{name}'");
        }

        public Database? GetDatabase(string name)
        {
            return _activeDatabases.GetValueOrDefault(name);
        }

        public (T, string) RegisterObject<T>(Func<T> generator, string? id = null) where T : class, IDisposable
        {
            var retVal = generator();
            var key = id ?? Guid.NewGuid().ToString();
            _activeDisposables.Add(key, retVal);
            return (retVal, key);
        }

        public void KeepAlive(object obj)
        {
            _keepAlives.Add(obj);
        }

        public T? GetObject<T>(string name) where T : class, IDisposable
        {
            if(!_activeDisposables.TryGetValue(name, out var retVal)) {
                return null;
            }

            return retVal as T;
        }

        private static string ToHexFolderName(byte[] bytes)
        {
            var sb = new StringBuilder(bytes.Length * 2);
            foreach (var b in bytes)
            {
                sb.Append(b.ToString("x2"));
            }
            return sb.ToString();
        }

        private async Task<Stream?> DownloadIfNecessary(Uri datasetUrl)
        {
            var localFile = datasetUrl.AbsolutePath.Split('/').Last();
            var subfolder = SHA1.HashData(Encoding.ASCII.GetBytes(datasetUrl.AbsolutePath));
            var downloadedPath = Path.Combine(_filesDirectory, "downloaded", ToHexFolderName(subfolder), localFile);
            if (File.Exists(downloadedPath)) {
                return File.OpenRead(downloadedPath);
            }

            var directory = Path.GetDirectoryName(downloadedPath);
            if (!string.IsNullOrEmpty(directory) && !Directory.Exists(directory)) {
                Directory.CreateDirectory(directory);
            }

            Stream retVal;
            try {
                retVal = await _httpClient.GetStreamAsync(datasetUrl).ConfigureAwait(false);
            } catch (HttpRequestException ex) {
                if(ex.StatusCode == HttpStatusCode.NotFound) {
                    return null;
                }

                throw;
            } catch (Exception ex) {
                throw new ApplicationException($"Unable to download item '{localFile}'", ex);
            }

            using var wl = await _lock.WriterLockAsync();
            await using (var fout = File.Create(downloadedPath)) {
                await retVal.CopyToAsync(fout).ConfigureAwait(false);
            }

            return File.OpenRead(downloadedPath);
        }
    }
}
