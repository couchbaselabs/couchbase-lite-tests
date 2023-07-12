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
package com.couchbase.lite.android.mobiletest.util

import com.couchbase.lite.mobiletest.Server
import java.net.Inet4Address
import java.net.Inet6Address
import java.net.InetAddress
import java.net.NetworkInterface
import java.net.URI
import java.net.URISyntaxException
import java.net.URLEncoder

const val TAG = "NETUTILS"

private class INetAddressComparator : Comparator<InetAddress> {
    enum class Scope { LOOPBACK, LOCAL, ROUTABLE }

    override fun compare(a1: InetAddress, a2: InetAddress) = when {
        (a1 is Inet4Address) && (a2 !is Inet4Address) -> -1
        (a2 is Inet4Address) && (a1 !is Inet4Address) -> 1
        else -> a2.scope().compareTo(a1.scope())
    }

    fun InetAddress.scope() = when {
        this.isLoopbackAddress -> Scope.LOOPBACK
        (this.isLinkLocalAddress || this.isSiteLocalAddress) -> Scope.LOCAL
        else -> Scope.ROUTABLE
    }
}

fun Inet6Address.asURIString(): String? {
    var addr = this.hostAddress ?: return null
    val p = addr.indexOf('%')
    if (p >= 0) addr = "${addr.substring(0, p)}%25${URLEncoder.encode(addr.substring(p + 1), "UTF-8")}"
    return "[${addr}]"
}

fun Server.url(scheme: String = "http", path: String = ""): URI? {
    val comparator = INetAddressComparator()
    val urls = NetworkInterface.getNetworkInterfaces().toList().mapNotNull {
        // get a sorted list of addresses, per up interface
        if (!it.isUp) {
            null
        } else {
            it.inetAddresses.toList().sortedWith(comparator)
        }
    }
        // remove any empty lists
        .mapNotNull { it.ifEmpty { null } }
        // sort the lists of addresses by their first address
        .sortedWith { a, b -> comparator.compare(a.first(), b.first()) }
        // flatten the lists
        .flatten()
        // convert the addresses to URLs
        .mapNotNull { addr ->
            val addrStr = if (addr is Inet4Address) {
                addr.hostAddress
            } else {
                // From LiteCore: As a heuristic, ignore interfaces that have _only_
                // link-local IPv6 addresses, since IPv6 requires that _every_ interface
                // have a link-local address. Such interfaces are likely to be inactive.
                if (addr.isLinkLocalAddress) return@mapNotNull null
                (addr as Inet6Address).asURIString()
            }

            addrStr ?: return@mapNotNull null
            try {
                URI("${scheme}://${addrStr}:${this.myPort}/${path}")
            } catch (err: URISyntaxException) {
                android.util.Log.d(TAG, "Bad URL from: ${addrStr}", err)
                null
            }
        }

    return if (urls.isNotEmpty()) urls[0] else null
}
