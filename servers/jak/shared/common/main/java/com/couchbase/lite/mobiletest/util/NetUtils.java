//
// Copyright (c) 2023 Couchbase, Inc All rights reserved.
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
// http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.
//
package com.couchbase.lite.mobiletest.util;

import androidx.annotation.NonNull;
import androidx.annotation.Nullable;

import java.io.IOException;
import java.io.UnsupportedEncodingException;
import java.net.Inet4Address;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.NetworkInterface;
import java.net.Socket;
import java.net.SocketException;
import java.net.URI;
import java.net.URISyntaxException;
import java.net.URLEncoder;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.List;

import edu.umd.cs.findbugs.annotations.SuppressFBWarnings;

import com.couchbase.lite.mobiletest.services.Log;


public final class NetUtils {
    private NetUtils() { }

    private static final String TAG = "NET_UTIL";

    public enum Scope {LOOPBACK, LOCAL, ROUTABLE}

    @SuppressFBWarnings("SE_COMPARATOR_SHOULD_BE_SERIALIZABLE")
    public static class INetAddressComparator implements Comparator<InetAddress> {
        public int compare(@NonNull InetAddress a1, @NonNull InetAddress a2) {
            if (a1 instanceof Inet4Address && !(a2 instanceof Inet4Address)) { return -1; }
            if (a2 instanceof Inet4Address && !(a1 instanceof Inet4Address)) { return 1; }
            return getAddrScope(a2).compareTo(getAddrScope(a1));
        }
    }

    @NonNull
    public static Scope getAddrScope(@NonNull InetAddress addr) {
        if (addr.isLoopbackAddress()) { return Scope.LOOPBACK; }
        if (!addr.isLinkLocalAddress() && !addr.isSiteLocalAddress()) { return Scope.ROUTABLE; }
        return Scope.LOCAL;
    }

    @SuppressWarnings({"PMD.AvoidReassigningParameters", "PMD.AvoidUsingHardCodedIP"})
    @Nullable
    public static URI makeUri(@Nullable String scheme, @Nullable String addr, int port, @Nullable String path) {
        if (scheme == null) { scheme = "http"; }
        if (addr == null) { addr = "0.0.0.0"; }
        if (port < 0) { port = 8080; }
        try { return new URI(scheme, null, addr, port, path, null, null); }
        catch (URISyntaxException e) {
            Log.err(TAG, "Cannot parse URI: " + scheme + "//:" + addr + ":" + port + "/" + path);
        }
        return null;
    }

    @Nullable
    public static String getLocalAddress() {
        try (Socket socket = new Socket()) {
            socket.connect(new InetSocketAddress("google.com", 80));
            return socket.getLocalAddress().getHostAddress();
        }
        catch (IOException e) { return null; }
// Old version:
//        final List<InetAddress> addrs = NetUtils.getLocalAddresses();
//        return (addrs == null) ? null : asString(addrs.get(0));
    }

    // Get a list of addresses for this host, sorted by usefulness
    @Nullable
    public static List<InetAddress> getLocalAddresses() {
        final List<NetworkInterface> ifaces;
        try { ifaces = Collections.list(NetworkInterface.getNetworkInterfaces()); }
        catch (SocketException e) {
            Log.err(TAG, "Failed getting network interfaces", e);
            return null;
        }

        final INetAddressComparator comparator = new INetAddressComparator();

        // get sorted lists of addresses for each interface
        final List<List<InetAddress>> addrs = new ArrayList<>();
        for (NetworkInterface iface: ifaces) {
            try {
                if (!iface.isUp()) { continue; }
            }
            catch (SocketException e) {
                Log.err(TAG, "Failed getting up state for interface " + iface, e);
                continue;
            }

            final List<InetAddress> ifaceAddrs = Collections.list(iface.getInetAddresses());
            if (ifaceAddrs.isEmpty()) { continue; }

            // sort the addresses in each list
            ifaceAddrs.sort(comparator);
            Log.p(TAG, "Considering interfaces:");
            for (InetAddress ifaceAddr: ifaceAddrs) { Log.p(TAG, "   > " + ifaceAddr); }
            addrs.add(ifaceAddrs);
        }

        if (addrs.isEmpty()) { return null; }

        // sort the lists of addresses by their first element
        addrs.sort((addrList1, addrList2) -> comparator.compare(addrList1.get(0), addrList2.get(0)));
        final List<InetAddress> allAddrs = new ArrayList<>();
        for (List<InetAddress> ifaceAddrs: addrs) { allAddrs.addAll(ifaceAddrs); }

        return allAddrs;
    }

    @Nullable
    public static String asString(@Nullable InetAddress inetAddress) {
        if (inetAddress == null) { return null; }
        String addr = inetAddress.getHostAddress();
        if ((addr == null) || (inetAddress instanceof Inet4Address)) { return addr; }
        final int p = addr.indexOf('%');
        if (p >= 0) {
            try { addr = addr.substring(0, p) + "%25" + URLEncoder.encode(addr.substring(p + 1), "UTF-8"); }
            catch (UnsupportedEncodingException e) { return null; }
        }
        return "[" + addr + "]";
    }
}
