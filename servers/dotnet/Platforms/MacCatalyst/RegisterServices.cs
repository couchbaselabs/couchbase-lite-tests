using TestServer.Platforms.MacCatalyst;
using TestServer.Services;

namespace TestServer.Platforms
{
    internal static class RegisterServices
    {
        public static MauiAppBuilder AddTestServerServices(this MauiAppBuilder builder)
        {
            builder.Services.AddSingleton<IDeviceInformation, DeviceInformation>();
            return builder;
        }
    }
}
