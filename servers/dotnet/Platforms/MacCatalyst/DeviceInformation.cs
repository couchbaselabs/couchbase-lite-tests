using TestServer.Services;
using Foundation;

namespace TestServer.Platforms.MacCatalyst
{
    internal sealed class DeviceInformation : IDeviceInformation
    {
        private readonly IDeviceInfo _mauiInfo = DeviceInfo.Current;

        public string Model => $"{_mauiInfo.Manufacturer} / {_mauiInfo.Model}";

        public string SystemName => "macOS";

        public string SystemVersion => $"{NSProcessInfo.ProcessInfo.OperatingSystemVersionString} via iOS {_mauiInfo.VersionString}".Replace("Version ", "");

        public string SystemApiVersion => SystemVersion;
    }
}

