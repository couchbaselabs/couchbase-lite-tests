namespace TestServer;

public partial class App
{
	public App()
	{
		InitializeComponent();

        Windows[0].Page = new AppShell();
	}
}
