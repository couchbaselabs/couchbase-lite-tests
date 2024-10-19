using Couchbase.Lite;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;
using System.IO.Compression;
using System.Text.Json;
using TestServer.Handlers;
using TestServer.Services;

namespace TestServer
{
    public sealed class ObjectManager
    {
        private readonly Dictionary<string, Database> _activeDatabases = new();
        private readonly Dictionary<string, IDisposable> _activeDisposables = new();
        private readonly HashSet<object> _keepAlives = new();
        private readonly AutoReaderWriterLock _lock = new AutoReaderWriterLock();
        private readonly IFileSystem _fileSystem = CBLTestServer.ServiceProvider.GetRequiredService<IFileSystem>();

        public readonly string FilesDirectory;

        public ObjectManager(string filesDirectory)
        {
            FilesDirectory = filesDirectory;
            Directory.CreateDirectory(FilesDirectory);
        }

        public void Reset()
        {
            using var l = _lock.GetWriteLock();

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

        public async Task LoadDatabase(string? datasetName, IEnumerable<string> targetDbNames, IEnumerable<string>? collections = null)
        {
            IEnumerable<string> targetsToCreate = default!;
            using (var rl = _lock.GetReadLock()) {
                targetsToCreate = targetDbNames.Where(x => !_activeDatabases.ContainsKey(x));
                if (!targetsToCreate.Any()) {
                    return;
                }
            }

            void CreateNewDatabases(string? datasetName, IEnumerable<string>? collections)
            {
                foreach (var targetName in targetsToCreate) {
                    if (Database.Exists(targetName, FilesDirectory)) {
                        Database.Delete(targetName, FilesDirectory);
                    }

                    var dbConfig = new DatabaseConfiguration
                    {
                        Directory = FilesDirectory
                    };

                    if (datasetName != null) {
                        Database.Copy(Path.Join(FilesDirectory, $"{datasetName}.cblite2"), targetName, dbConfig);
                        _activeDatabases[targetName] = new Database(targetName, dbConfig);
                    } else {
                        var newDb = new Database(targetName, dbConfig);
                        _activeDatabases[targetName] = newDb;
                        if (collections != null) {
                            foreach (var c in collections) {
                                var collSpec = HandlerList.CollectionSpec(c);
                                using var coll = newDb.CreateCollection(collSpec.name, collSpec.scope);
                            }
                        }
                    }

                }
            }

            if(datasetName == null) {
                CreateNewDatabases(null, collections);
                return;
            }

            Stream asset;
            try {
                asset = await _fileSystem.OpenAppPackageFileAsync($"{datasetName}.cblite2.zip");
            } catch (Exception ex) {
                throw new ApplicationException($"Unable to open dataset '{datasetName}'", ex);
            }

            var destinationZip = Path.Combine(FilesDirectory, $"{datasetName}.cblite2.zip");
            using var wl = _lock.GetWriteLock();
            if (File.Exists(destinationZip)) {
                File.Delete(destinationZip);
            }

            using (var fout = File.OpenWrite(destinationZip)) {
                asset.CopyTo(fout);
                asset.Dispose();
            }

            if (Database.Exists(datasetName, FilesDirectory)) {
                Database.Delete(datasetName, FilesDirectory);
            }

            ZipFile.ExtractToDirectory(destinationZip, FilesDirectory);
            CreateNewDatabases(datasetName, null);
            Database.Delete(datasetName, FilesDirectory);
        }

        public async Task<Stream> LoadBlob(string name)
        {
            Stream asset;
            try {
                asset = await _fileSystem.OpenAppPackageFileAsync($"blobs/{name}");
            } catch (FileNotFoundException) {
                throw new JsonException($"Request for nonexistent blob '{name}'");
            } catch (Exception ex) {
                throw new ApplicationException($"Unable to open blob '{name}'", ex);
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
