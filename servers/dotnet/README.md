# .NET TestServer

The .NET implementation of the Couchbase Lite test server. Two entry points
share the logic in `testserver.logic`:

- `testserver/` — a .NET MAUI app targeting `net10.0-ios`, `net10.0-maccatalyst`,
  and `net10.0-android` (iOS, Mac Catalyst, Android).
- `testserver.cli/` — a `net8.0` console app for Windows / desktop.
- `testserver.logic/` — shared server logic (handlers, routing) used by both.

## Requirements

- .NET SDK — versions are pinned by `global.json`. The MAUI app needs the .NET 10
  SDK plus the MAUI workloads; the CLI needs .NET 8.
- For the MAUI (mobile / Mac Catalyst) targets: Visual Studio or Rider with the
  MAUI workload installed.
- NuGet feeds are configured in `nuget.config`.

## Build and Run

Build with the standard .NET toolchain, either from an IDE (open
`testserver.sln`) or the CLI. For the desktop / Windows CLI server:

```
dotnet build testserver.sln
dotnet run --project testserver.cli
```

The MAUI app (`testserver`) is built and deployed to a device, simulator, or Mac
Catalyst from your IDE in the usual way. Running .NET apps locally is assumed
knowledge — this README only documents what is specific to this project.

> In CI the server is built by the orchestrator
> (`environment/aws/topology_setup/test_server_platforms/dotnet_register.py`),
> which runs `dotnet publish` after pinning the `Couchbase.Lite.Enterprise`
> package version. There is no standalone build script.

See [servers/AGENTS.md](../AGENTS.md) for the layered architecture every server
shares and the full endpoint list.
