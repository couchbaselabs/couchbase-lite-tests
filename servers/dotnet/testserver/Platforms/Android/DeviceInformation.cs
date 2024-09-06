using TestServer.Services;
using Droid = global::Android;

namespace TestServer.Platforms.Android
{
    internal sealed class DeviceInformation : IDeviceInformation
    {
        private readonly IDeviceInfo _mauiInfo = DeviceInfo.Current;

        public string Model => $"{_mauiInfo.Manufacturer} / {_mauiInfo.Model}";

        public string SystemName => "Android";

        public string SystemVersion => Droid.OS.Build.VERSION.Release ?? Droid.OS.Build.VERSION.Codename ?? "unknown";

        public string SystemApiVersion => $"{(int)Droid.OS.Build.VERSION.SdkInt}";
    }
}
