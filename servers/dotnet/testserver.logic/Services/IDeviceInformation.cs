using System.Text.Json.Serialization;
using JetBrains.Annotations;

namespace TestServer.Services
{
    public interface IDeviceInformation
    {
        [JsonPropertyName("model")] 
        [UsedImplicitly]
        string Model { get; }

        [JsonPropertyName("systemName")]
        [UsedImplicitly]
        string SystemName { get; }

        [JsonPropertyName("systemVersion")]
        [UsedImplicitly]
        string SystemVersion { get; }

        [JsonPropertyName("systemApiVersion")]
        [UsedImplicitly]
        string SystemApiVersion { get; }
    }
}
