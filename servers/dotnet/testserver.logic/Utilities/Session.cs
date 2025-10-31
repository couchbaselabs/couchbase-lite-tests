using Microsoft.Extensions.DependencyInjection;
using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Linq;
using System.Net;
using System.Text;
using System.Threading.Tasks;
using TestServer.Services;

namespace TestServer.Utilities
{
    internal sealed class Session : IDisposable
    {
        private readonly string _id;
        private static readonly Dictionary<string, Session> ActiveSessions = new();

        public ObjectManager ObjectManager { get; }

        private Session(IServiceProvider serviceProvider, string id, string datasetVersion)
        {
            var fileSystem = serviceProvider.GetRequiredService<IFileSystem>();
            ObjectManager = new ObjectManager(Path.Join(fileSystem.AppDataDirectory, "testfiles"), datasetVersion);
            _id = id;
        }

        public static void Create(IServiceProvider serviceProvider, string id, string datasetVersion)
        {
            if(ActiveSessions.ContainsKey(id)) {
                throw new BadRequestException($"Session '{id}' already started");
            }

            // This may change later, but for now creating a new session invalidates the old
            foreach (var session in ActiveSessions) {
                session.Value.Dispose();
            }

            ActiveSessions.Clear();
            ActiveSessions[id] = new Session(serviceProvider, id, datasetVersion);
        }

        public static Session For(string? id)
        {
            if (id == null) {
                throw new ApplicationStatusException($"Header '{Router.ClientIdHeader}' missing", HttpStatusCode.BadRequest);
            }

            if (!ActiveSessions.TryGetValue(id, out var session)) {
                throw new BadRequestException($"Session '{id}' never started or already finished!");
            }

            return session;
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
