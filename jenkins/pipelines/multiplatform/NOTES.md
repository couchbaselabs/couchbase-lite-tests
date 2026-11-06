# Multiplatform pipeline: open work

## Windows and Linux test servers cannot take part

The pipeline runs on the `qe-mac-india` agent. `topology.json` lists the 8 iPhones and 8 Android devices attached
to it, plus `c_macos` and `dotnet_macos` on the Mac itself. Desktop test servers (`c_windows`, `c_linux_x86_64`,
`dotnet_windows`, `jak_desktop`, `jak_webservice`) only run on the agent itself (`location: localhost`), so none of
the Windows or Linux platforms can be exercised. Asking for one fails the sanity check ("the topology has 0") and
the build ends UNSTABLE.

### Constraints

1. **One agent per run.** A run on a Windows or Linux agent can only use that machine's desktop test servers. It
   cannot mix them with the iOS or Android devices on the Mac.
2. **Fixed ports.** The orchestrator starts every test server on a fixed port
   (`environment/aws/topology_setup/test_server.py`): C on 8080, .NET on 5555, Java desktop and Java web service on
   8080. One host can therefore run C + .NET or Java + .NET, but not C with Java, and never two test servers of
   the same platform. The Java servers already accept `--port` and the C server takes its port as an argument,
   but the orchestrator passes neither.
3. **Windows needs PowerShell.** Windows agents run pipeline steps through `pwsh` and `.ps1` scripts, while
   `test_multiplatform.sh` and `teardown.sh` are bash only.

### Plan

1. Per-server ports in `environment/aws/topology_setup`: let a topology entry set `port`, pass it to the C and
   Java test servers, and record it in the TDK config. This also allows two test servers of one platform per host.
2. `topology_windows.json` (`c_windows`, `dotnet_windows`, `jak_desktop`, `jak_webservice`) and
   `topology_linux.json` (`c_linux_x86_64`, `jak_desktop`, `jak_webservice`), with distinct ports and the same
   Couchbase Server and Sync Gateway backend as `topology.json`.
3. The Jenkinsfile picks the agent from `TOPOLOGY_FILE`: `qe-mac-india` for `topology.json`,
   `e2e&&windows-host` for Windows, `e2e&&linux-host` for Linux. Lock the chosen node, since those pools also run
   the functional pipelines.
4. `test_multiplatform.ps1` and `teardown.ps1` for the Windows path.
5. A sanity check in `setup_multiplatform.py` that rejects selected `localhost` test servers sharing a port.

### Open questions

- Does the `e2e&&windows-host` pool have the .NET SDK that `dotnet_windows` needs?
- Is peer-to-peer between test servers on one host (loopback) enough, or do we want cross-host runs? Those need
  test servers started on remote hosts, which `ExeBridge` cannot do today.

## Related

- **Unused backend.** `topology.json` always provisions a Couchbase Server and a Sync Gateway, which multipeer and
  peer-to-peer runs never use (see the TODO in `setup_multiplatform.py`).
- **Test server order.** `match_topology()` in `setup_multiplatform.py` sorts the selected test servers into
  topology order, not `PLATFORM_VERSIONS` order. Tests use `test_servers[0]`, `[1]`, `[2]`, so a run cannot choose
  which platform takes which role in a peer-to-peer test.
- **Device IP hints.** Android devices `51131XEKB7DBF1` and `R58M87C818K` in `topology.json` share `ip_hint`
  `172.16.150.163`, carried over from the old topologies. One of them is probably wrong.
