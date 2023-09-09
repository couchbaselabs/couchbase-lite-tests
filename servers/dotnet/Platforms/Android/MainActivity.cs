using Android.App;
using Android.Content.PM;
using Android.OS;

namespace TestServer;

[Activity(Theme = "@style/Maui.SplashTheme",  Name = "com.couchbase.dotnet.testserver.MainActivity", MainLauncher = true, ConfigurationChanges = ConfigChanges.ScreenSize | ConfigChanges.Orientation | ConfigChanges.UiMode | ConfigChanges.ScreenLayout | ConfigChanges.SmallestScreenSize | ConfigChanges.Density)]
public class MainActivity : MauiAppCompatActivity
{
}
