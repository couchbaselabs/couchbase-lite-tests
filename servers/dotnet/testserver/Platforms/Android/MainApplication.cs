using Android.App;
using Android.Runtime;

namespace TestServer;

[Application]
public class MainApplication : MauiApplication
{
	public MainApplication(IntPtr handle, JniHandleOwnership ownership)
		: base(handle, ownership)
	{
	}

    protected override MauiApp CreateMauiApp()
    {
        Couchbase.Lite.Support.Droid.Activate(ApplicationContext);
        return MauiProgram.CreateMauiApp();
    }
}
