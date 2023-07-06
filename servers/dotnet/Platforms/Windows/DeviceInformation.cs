using TestServer.Services;

namespace TestServer.Platforms.Windows
{
    internal sealed class DeviceInformation : IDeviceInformation
    {
        private readonly IDeviceInfo _mauiInfo = DeviceInfo.Current;

        public string Model => $"{_mauiInfo.Manufacturer} / {_mauiInfo.Model}";

        public string SystemName => "Windows";

        public string SystemVersion => _mauiInfo.VersionString;

        public string SystemApiVersion => _mauiInfo.VersionString;
    }
}
