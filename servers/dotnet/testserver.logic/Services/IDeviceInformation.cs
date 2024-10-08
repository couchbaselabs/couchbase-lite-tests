﻿using System.Text.Json.Serialization;

namespace TestServer.Services
{
    public interface IDeviceInformation
    {
        [JsonPropertyName("model")]
        string Model { get; }

        [JsonPropertyName("systemName")]
        string SystemName { get; }

        [JsonPropertyName("systemVersion")]
        string SystemVersion { get; }

        [JsonPropertyName("systemApiVersion")]
        string SystemApiVersion { get; }
    }
}
