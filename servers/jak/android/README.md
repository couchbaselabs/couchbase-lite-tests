1. Open settings.gradle in Android studio to sources the project.
2. MainActivity.kt is the launcher activity to launch APP.

* Simply running the project will launch the app on the emulator or device of your choice.
* Currently we are not displaying the IP of the emulator/device in app and we are using Port 8080 for
HTTP server. So if you have the port used elsewhere, do change to an unused port no.
* One can find the IP address of device by going in settings -> About Phone -> status -> IP address.

Updating CBL API references -
* Go to App level build.gradle and change the "COUCHBASE_LITE_VERSION" variable to update API references

Note - We are using NanoHttpServer to run a http server.
To change the reference APIs modified below line in app level build.gradle
==> compile "org.nanohttpd:nanohttpd:2.3.2-SNAPSHOT" <==


