using Microsoft.Extensions.DependencyInjection;
using System.Net;
using TestServer.Services;

namespace TestServer.Utilities
{
    internal sealed class Session : IDisposable
    {
        private readonly string _id;
        private static readonly Dictionary<string, Session> ActiveSessions = new();

        public ObjectManager ObjectManager { get; }

        private Session(IServiceProvider serviceProvider, string id)
        {
            var fileSystem = serviceProvider.GetRequiredService<IFileSystem>();
            ObjectManager = new ObjectManager(Path.Join(fileSystem.AppDataDirectory, "testfiles"));
            _id = id;
        }

        public static void Create(IServiceProvider serviceProvider, string id)
        {
            if(ActiveSessions.ContainsKey(id)) {
                throw new BadRequestException($"Session '{id}' already started");
            }

            // This may change later, but for now creating a new session invalidates the old
            foreach (var session in ActiveSessions) {
                session.Value.Dispose();
            }

            ActiveSessions.Clear();
            ActiveSessions[id] = new Session(serviceProvider, id);
        }

        public static Session For(string? id)
        {
            if (id == null) {
                throw new ApplicationStatusException($"Header '{Router.ClientIdHeader}' missing", HttpStatusCode.BadRequest);
            }

            return !ActiveSessions.TryGetValue(id, out var session) 
                ? throw new BadRequestException($"Session '{id}' never started or already finished!") 
                : session;
        }

        public override string ToString()
        {
            return $"Session '{_id}'";
        }

        public void Dispose()
        {
            ObjectManager.Reset();
        }
    }
}
