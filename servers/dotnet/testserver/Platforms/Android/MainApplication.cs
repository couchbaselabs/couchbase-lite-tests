using System.Diagnostics;
using Android.App;
using Android.Runtime;

namespace TestServer;

[Application]
public class MainApplication(IntPtr handle, JniHandleOwnership ownership) : MauiApplication(handle, ownership)
{
    protected override MauiApp CreateMauiApp()
    {
        Debug.Assert(ApplicationContext != null, nameof(ApplicationContext) + " != null");
        Couchbase.Lite.Support.Droid.Activate(ApplicationContext);
        return MauiProgram.CreateMauiApp();
    }
}
