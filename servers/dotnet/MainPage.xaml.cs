using System.Net;
using System.Net.Sockets;
using System.Reflection;

namespace TestServer;

public partial class MainPage : ContentPage
{
	public MainPage()
	{
		InitializeComponent();

		var server = new CBLTestServer();
		server.Start();
	}

    protected override void OnAppearing()
    {
        base.OnAppearing();

		_versionLabel.Text = "CBL Version: " + typeof(Couchbase.Lite.Database).Assembly.GetCustomAttribute<AssemblyInformationalVersionAttribute>()!.InformationalVersion;
        var host = Dns.GetHostEntry(Dns.GetHostName());
        var ipAddresses = "Server running at:" + 
			Environment.NewLine + 
			String.Join(Environment.NewLine, host.AddressList
			.Where(x => x.AddressFamily == AddressFamily.InterNetwork)
			.Select(x => $"http://{x}:8080"));
		_urlLabel.Text = ipAddresses;
    }
}

