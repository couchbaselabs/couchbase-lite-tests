using Couchbase.Lite;
using Microsoft.Extensions.Logging;
using System.IO.Compression;

namespace TestServer
{
    public sealed class ObjectManager
    {
        private readonly Dictionary<string, Database> _activeDatabases = new();
        private readonly Dictionary<string, IDisposable> _activeDisposables = new();
        private readonly HashSet<object> _keepAlives = new();
        private readonly AutoReaderWriterLock _lock = new AutoReaderWriterLock();
        private readonly ILogger<ObjectManager> _logger = MauiProgram.ServiceProvider.GetRequiredService<ILoggerFactory>().CreateLogger<ObjectManager>();

        public readonly string FilesDirectory;

        public ObjectManager(string filesDirectory)
        {
            FilesDirectory = filesDirectory;
            Directory.CreateDirectory(FilesDirectory);
        }

        public void Reset()
        {
            using var l = _lock.GetWriteLock();

            foreach (var d in _activeDisposables) {
                d.Value.Dispose();
            }

            _activeDisposables.Clear();

            foreach (var db in _activeDatabases) {
                try {
                    db.Value.Delete();
                    db.Value.Dispose();
                } catch (Exception ex) {
                    _logger.LogWarning(ex, "Failed to delete/dispose {name}", db.Value.Name);
                }
            }

            _activeDatabases.Clear();
            _keepAlives.Clear();
        }

        public async Task LoadDataset(string name, IEnumerable<string> targetDbNames)
        {
            IEnumerable<string> targetsToCreate = default!;
            using (var rl = _lock.GetReadLock()) {
                targetsToCreate = targetDbNames.Where(x => !_activeDatabases.ContainsKey(x));
                if (!targetsToCreate.Any()) {
                    return;
                }
            }

            void CreateNewDatabases(string datasetName)
            {
                foreach (var targetName in targetsToCreate) {
                    if (Database.Exists(targetName, FilesDirectory)) {
                        Database.Delete(targetName, FilesDirectory);
                    }

                    var dbConfig = new DatabaseConfiguration
                    {
                        Directory = FilesDirectory
                    };

                    if (datasetName != "empty") {
                        Database.Copy(Path.Join(FilesDirectory, $"{name}.cblite2"), targetName, dbConfig);
                    }

                    _activeDatabases[targetName] = new Database(targetName, dbConfig);
                }
            }

            if(name == "empty") {
                CreateNewDatabases(name);
                return;
            }

            Stream asset;
            try {
                asset = await FileSystem.OpenAppPackageFileAsync($"{name}.cblite2.zip");
            } catch (Exception ex) {
                throw new ApplicationException($"Unable to open dataset '{name}'", ex);
            }

            var destinationZip = Path.Combine(FilesDirectory, $"{name}.cblite2.zip");
            using var wl = _lock.GetWriteLock();
            if (File.Exists(destinationZip)) {
                File.Delete(destinationZip);
            }

            using (var fout = File.OpenWrite(destinationZip)) {
                asset.CopyTo(fout);
                asset.Dispose();
            }

            if (Database.Exists(name, FilesDirectory)) {
                Database.Delete(name, FilesDirectory);
            }

            CreateNewDatabases(name);
            Database.Delete(name, FilesDirectory);
        }

        public async Task<Stream> LoadBlob(string name)
        {
            Stream asset;
            try {
                asset = await FileSystem.OpenAppPackageFileAsync($"blobs/{name}");
            } catch (Exception ex) {
                throw new ApplicationException($"Unable to open dataset '{name}'", ex);
            }

            return asset;
        }

        public Database? GetDatabase(string name)
        {
            return _activeDatabases.TryGetValue(name, out var db) ? db : null;
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
                return default;
            }

            if(retVal is not T castVal) {
                return default;
            }

            return castVal;
        }
    }
}
