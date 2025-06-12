# This app complies with Couchbase Lite Test Server REST API v1.1,1

# Running the project
1. Open build.gradle with Android Studio
2. Use MainActivity.kt to launch the app

Updating CBL API references -
* Go to App level build.gradle and change the "COUCHBASE_LITE_VERSION" variable to update API references

Note - We are using NanoHttpServer to run a http server.
To change the reference APIs modify the below line in app level build.gradle
==> compile "org.nanohttpd:nanohttpd:2.3.2-SNAPSHOT" <==


