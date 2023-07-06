using Couchbase.Lite;
using System.IO.Compression;

namespace TestServer
{
    public sealed class ObjectManager
    {
        private readonly Dictionary<string, Database> _activeDatabases = new();
        private readonly HashSet<IDisposable> _activeDisposables = new();
        private readonly AutoReaderWriterLock _lock = new AutoReaderWriterLock();

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
                d.Dispose();
            }

            _activeDisposables.Clear();

            foreach(var db in _activeDatabases) {
                db.Value.Delete();
                db.Value.Dispose();
            }

            _activeDatabases.Clear();
        }

        public async Task LoadDataset(string name, IEnumerable<string> targetDbNames)
        {
            using (var rl = _lock.GetReadLock()) {
                if (_activeDatabases.ContainsKey(name)) {
                    return;
                }
            }

            Stream asset;
            try {
                asset = await FileSystem.OpenAppPackageFileAsync($"{name}.cblite2.zip");
            } catch (Exception ex) {
                throw new ApplicationException($"Unable to open dataset '{name}'", ex);
            }

            var destinationZip = Path.Combine(FilesDirectory, $"{name}.cblite2.zip");
            using var wl = _lock.GetWriteLock();
            if(File.Exists(destinationZip)) {
                File.Delete(destinationZip);
            }

            using (var fout = File.OpenWrite(destinationZip)) {
                asset.CopyTo(fout);
                asset.Dispose();
            }

            if(Database.Exists(name, FilesDirectory)) {
                Database.Delete(name, FilesDirectory);
            }

            ZipFile.ExtractToDirectory(destinationZip, FilesDirectory);
            File.Delete(destinationZip);

            foreach(var targetDbName in targetDbNames) {
                if(Database.Exists(targetDbName, FilesDirectory)) {
                    Database.Delete(targetDbName, FilesDirectory);
                }

                var dbConfig = new DatabaseConfiguration
                {
                    Directory = FilesDirectory
                };

                Database.Copy(Path.Join(FilesDirectory, $"{name}.cblite2"), targetDbName, dbConfig);
                _activeDatabases[targetDbName] = new Database(targetDbName, dbConfig);
            }

            Database.Delete(name, FilesDirectory);
        }

        public Database? GetDatabase(string name)
        {
            return _activeDatabases.TryGetValue(name, out var db) ? db : null;
        }

        public T RegisterObject<T>(Func<T> generator) where T : IDisposable
        {
            var retVal = generator();
            _activeDisposables.Add(retVal);
            return retVal;
        }
    }
}
