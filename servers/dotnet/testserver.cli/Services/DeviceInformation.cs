using System;
using System.Collections.Generic;
using System.Linq;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading.Tasks;
using TestServer.Services;

namespace TestServer.Cli.Services
{
    internal sealed class DeviceInformation : IDeviceInformation
    {
        public string Model => $"CLI {RuntimeInformation.FrameworkDescription}";

        public string SystemName
        {
            get {
                if (RuntimeInformation.IsOSPlatform(OSPlatform.Windows)) {
                    return "Windows";
                } else if (RuntimeInformation.IsOSPlatform(OSPlatform.OSX)) {
                    return "macOS";
                } else {
                    return "Linux";
                }
            }
        }

        public string SystemVersion => RuntimeInformation.OSDescription;

        public string SystemApiVersion => RuntimeInformation.OSDescription;
    }
}
