# JVM / Kotlin TestServer (`jak`)

The Java/Kotlin implementation of the Couchbase Lite test server, sharing code in
`shared/` across three variants:

- `desktop/` — JVM desktop server (runnable JAR)
- `webservice/` — Jetty-hosted web service
- `android/` — Android app (APK)

Couchbase Lite is pulled in as a Gradle dependency (selected by `-PcblVersion`),
so there is no separate download step. The server's own version lives in
`version.txt`.

## Requirements

- Java 17+
- Android: Android Studio + SDK (for the `android` variant)
- The Gradle wrapper (`gradlew`) is bundled in each variant — no separate Gradle
  install needed.

## Build

Each variant builds from its own directory with the Gradle wrapper, passing the
CBL version (`<version>-<build>`) and dataset version. These are the same
invocations the orchestrator's `java_register.py` uses.

Desktop and web service (produce a runnable JAR):

```
cd desktop      # or: cd webservice
./gradlew jar -PcblVersion=4.0.0-43 -PdatasetVersion=3.2
```

Android (produces an APK):

```
cd android
./gradlew assembleRelease -PcblVersion=4.0.0-43 -PdatasetVersion=3.2
```

On Windows use `gradlew.bat` and add `--no-daemon`.

## Run

**Desktop** — run the built JAR with the `server` argument:

```
java -jar desktop/app/build/libs/CBLTestServer-Java-Desktop-<server-version>_<cbl-version>.jar server
```

**Web service** — start / stop via Gradle (Jetty):

```
cd webservice
./gradlew jettyStart -PcblVersion=4.0.0-43 -PdatasetVersion=3.2   # start
./gradlew appStop    -PcblVersion=4.0.0-43 -PdatasetVersion=3.2   # stop
```

**Android** — install the built APK on a device / emulator (app id
`com.couchbase.lite.android.mobiletest`):

```
adb install android/app/build/outputs/apk/release/app-release.apk
```

> On Linux the desktop / web service variants need the Couchbase Lite Java
> support libraries (`libstdc++.so.6`, …) on `LD_LIBRARY_PATH`; the orchestrator
> downloads these automatically (see `java_register.py`).

See [servers/AGENTS.md](../AGENTS.md) for the shared architecture and the full
endpoint list.
