using System.Net;
using System.Net.NetworkInformation;
using System.Net.Sockets;
using System.Reflection;

namespace TestServer;

public partial class MainPage : ContentPage
{
    private const int PortToUse = 5555;

	public MainPage()
	{
		InitializeComponent();

		var server = new CBLTestServer
        {
            Port = PortToUse
        };
		server.Start();
	}

    private static bool IsInterfaceValid(NetworkInterface ni)
    {
        if (ni.OperationalStatus != OperationalStatus.Up) {
            return false;
        }

        if (ni.NetworkInterfaceType == NetworkInterfaceType.Loopback || ni.NetworkInterfaceType == NetworkInterfaceType.Tunnel
            || ni.Description.IndexOf("Loopback", StringComparison.OrdinalIgnoreCase) >= 0) {
            return false;
        }

        if (ni.Description.IndexOf("virtual", StringComparison.OrdinalIgnoreCase) >= 0) {
            return false;
        }

        return true;
    }

    protected override void OnAppearing()
    {
        base.OnAppearing();

        _versionLabel.Text = "Test Server Version: " + CBLTestServer.Version;
        _cblVersionLabel.Text = "CBL Version: " + typeof(Couchbase.Lite.Database).Assembly.GetCustomAttribute<AssemblyInformationalVersionAttribute>()!.InformationalVersion;

        var validIPs = NetworkInterface.GetAllNetworkInterfaces().Where(IsInterfaceValid)
                    .SelectMany(x => x.GetIPProperties().UnicastAddresses)
                    .Where(x => x.Address.AddressFamily == AddressFamily.InterNetwork && x.Address.GetAddressBytes()[0] != 169);

        var ipAddresses = "Server running at:" +
            Environment.NewLine +
            String.Join(Environment.NewLine, validIPs
            .Select(x => $"http://{x.Address}:{PortToUse}"));
        _urlLabel.Text = ipAddresses;
    }
}

