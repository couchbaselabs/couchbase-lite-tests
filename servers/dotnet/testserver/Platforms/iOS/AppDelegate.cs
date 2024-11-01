using System.Net;
using System.Net.NetworkInformation;
using System.Net.Sockets;
using System.Text;

using Foundation;

using Microsoft.Maui.LifecycleEvents;

using UIKit;

using Makaretu.Dns;

namespace TestServer;

[Register("AppDelegate")]
public class AppDelegate : MauiUIApplicationDelegate
{
	private const string SERVICE_RECORD_NAME = "_testserver._tcp";

	private ServiceProfile? _serviceProfile;
	private ServiceDiscovery? _serviceDiscovery;
	protected override MauiApp CreateMauiApp() => MauiProgram.CreateMauiApp();

	public override bool FinishedLaunching(UIApplication application, NSDictionary launchOptions)
	{
		var retVal = base.FinishedLaunching(application, launchOptions);

		Task.Run(() =>
		{
			var ipAddress = GetIpAddress();
			if (ipAddress == null) {
				return;
			}
			
			_serviceProfile = new ServiceProfile(ipAddress.Replace('.', '-'), SERVICE_RECORD_NAME, 8888);
			_serviceDiscovery = new();
			_serviceDiscovery.Advertise(_serviceProfile);
		});
		return retVal;
	}

	private string? GetIpAddress()
	{
		return NetworkInterface.GetAllNetworkInterfaces().FirstOrDefault(nic => nic.Name == "en0")
			?.GetIPProperties().UnicastAddresses
			.FirstOrDefault(addr => addr.Address.AddressFamily == AddressFamily.InterNetwork)?.Address.ToString();
	}
}
