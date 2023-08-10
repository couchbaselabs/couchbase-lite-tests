using TestServer.Services;

namespace TestServer.Platforms.iOS
{
    internal sealed class DeviceInformation : IDeviceInformation
    {
        private readonly IDeviceInfo _mauiInfo = DeviceInfo.Current;

        public string Model => $"{_mauiInfo.Manufacturer} / {_mauiInfo.Model}";

        public string SystemName => "iOS";

        public string SystemVersion => _mauiInfo.VersionString;

        public string SystemApiVersion => _mauiInfo.VersionString;
    }
}
