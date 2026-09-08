using System.Net.NetworkInformation;
using System.Net.Sockets;
using System.Reflection;

namespace TestServer;

public partial class MainPage
{
    private const int PORT_TO_USE = 5555;

    public MainPage()
    {
        InitializeComponent();

        var server = new CBLTestServer
        {
            Port = PORT_TO_USE
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

        return ni.Description.IndexOf("virtual", StringComparison.OrdinalIgnoreCase) < 0;
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
            .Select(x => $"http://{x.Address}:{PORT_TO_USE}"));
        _urlLabel.Text = ipAddresses;
    }
}

