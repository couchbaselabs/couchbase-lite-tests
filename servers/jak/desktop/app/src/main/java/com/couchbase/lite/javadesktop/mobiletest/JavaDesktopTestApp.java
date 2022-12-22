package com.couchbase.lite.javadesktop.mobiletest;

import androidx.annotation.NonNull;
import androidx.annotation.Nullable;

import java.net.Inet4Address;
import java.net.InetAddress;
import java.net.NetworkInterface;
import java.net.SocketException;
import java.net.UnknownHostException;
import java.util.Collections;
import java.util.Enumeration;

import com.couchbase.lite.mobiletest.BaseTestApp;
import com.couchbase.lite.mobiletest.util.Log;


public class JavaDesktopTestApp extends BaseTestApp {

    @NonNull
    @Override
    public String getPlatform() { return "java-desktop"; }

    @NonNull
    @Override
    public String getAppId() {
        try {
            final Enumeration<NetworkInterface> nets = NetworkInterface.getNetworkInterfaces();
            for (NetworkInterface iface: Collections.list(nets)) {
                final String iFaceName = iface.getName();
                if ("en0".equals(iFaceName) || "en1".equals(iFaceName)) {
                    final String ip = getIpAddressByInterface(iface);
                    if (ip != null) { return ip; }
                }
            }
            return InetAddress.getLocalHost().getHostAddress();
        }
        catch (SocketException | UnknownHostException e) { Log.w(TAG, "Failed getting device IP address", e); }
        return "unknown";
    }

    @Nullable
    private String getIpAddressByInterface(@NonNull NetworkInterface networkInterface) {
        for (InetAddress address: Collections.list(networkInterface.getInetAddresses())) {
            if (address instanceof Inet4Address) { return address.getHostAddress(); }
        }
        return null;
    }
}
