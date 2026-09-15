using System.Runtime.InteropServices;
using TestServer.Services;

namespace TestServer.Cli.Services
{
    internal sealed class DeviceInformation : IDeviceInformation
    {
        public string Model => $"CLI {RuntimeInformation.FrameworkDescription}";

        public string SystemName
        {
            get
            {
                if (RuntimeInformation.IsOSPlatform(OSPlatform.Windows)) {
                    return "Windows";
                }

                return RuntimeInformation.IsOSPlatform(OSPlatform.OSX) ? "macOS" : "Linux";
            }
        }

        public string SystemVersion => RuntimeInformation.OSDescription;

        public string SystemApiVersion => RuntimeInformation.OSDescription;
    }
}
