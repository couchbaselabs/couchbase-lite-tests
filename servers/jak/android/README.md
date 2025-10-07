# Android test server
This app complies with Couchbase Lite Test Server REST API v1.2.1

# Running the project
1. Open build.gradle as a project with Android Studio
2. Select an attached phone or start an emulator
3. Use the arrow in the gutter next to the class declaration in MainActivity.kt to launch the app (or use the Run menu)

There are two ways of setting the version of CBL Android to be tested:

- On your local machine, in ~/.gradle/gradle.properties define `cblVersion`.  E.g., `cblVersion=3.3.0-33`
- At compile time, define the property `cblVersion` on the command line.  E.g., `./gradlew assemble -PcblVersion=...`

Note - This project uses NanoHttpServer to run an http server.  That project seems to be moribund.  If you ever need to change the version used here, change this line:

    implementation "org.nanohttpd:nanohttpd:2.3.2-SNAPSHOT"
    
... in app/build.gradle
