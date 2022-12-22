//
// Copyright (c) 2022 Couchbase, Inc All rights reserved.
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
package com.couchbase.lite.android.mobiletest

import android.content.Context
import android.util.Base64
import com.couchbase.lite.CouchbaseLite
import com.couchbase.lite.CouchbaseLiteException
import com.couchbase.lite.KeyStoreUtils
import com.couchbase.lite.TLSIdentity
import com.couchbase.lite.mobiletest.TestApp
import com.couchbase.lite.mobiletest.util.Log
import java.io.IOException
import java.net.Inet4Address
import java.net.NetworkInterface
import java.net.SocketException
import java.security.KeyStoreException
import java.security.NoSuchAlgorithmException
import java.security.UnrecoverableEntryException
import java.security.cert.CertificateException
import java.util.*


class AndroidTestApp(private val context: Context) : TestApp() {

    override fun initCBL() {
        CouchbaseLite.init(context, true)
    }

    override fun getPlatform() = "android"

    override fun getFilesDir() = context.filesDir

    override fun getAsset(name: String) = context.getAssets().open(name)

    override fun encodeBase64(hashBytes: ByteArray) = Base64.encodeToString(hashBytes, Base64.NO_WRAP)

    override fun decodeBase64(encodedBytes: String) = Base64.decode(encodedBytes, Base64.NO_WRAP)

    override fun getAppId(): String {
        try {
            for (intf in Collections.list(NetworkInterface.getNetworkInterfaces())) {
                val iFaceName = intf.name
                Log.d(TAG, "intf_name: $iFaceName")
                for (inetAddress in Collections.list(intf.inetAddresses)) {
                    if (!inetAddress.isLoopbackAddress
                        && inetAddress is Inet4Address
                        && (iFaceName == "eth1" || iFaceName == "wlan0") // ???
                    ) {
                        inetAddress.getHostAddress()?.let { return it }
                    }
                }
            }
        } catch (e: SocketException) {
            Log.w(TAG, "Failed getting device IP address", e)
        }
        return "unknown"
    }

    @Throws(CouchbaseLiteException::class)
    override fun getCreateIdentity(): TLSIdentity {
        return TLSIdentity.createIdentity(
            true,
            x509Attributes,
            expirationTime,
            UUID.randomUUID().toString()
        )
    }

    @Throws(
        UnrecoverableEntryException::class,
        CertificateException::class,
        KeyStoreException::class,
        NoSuchAlgorithmException::class,
        IOException::class,
        CouchbaseLiteException::class
    )
    override fun getSelfSignedIdentity(): TLSIdentity {
        val serverCert = getAsset("certs.p12")
        KeyStoreUtils.importEntry(
            "PKCS12",
            serverCert,
            "123456".toCharArray(),
            "testkit",
            "123456".toCharArray(),
            "Servercerts"
        )
        return TLSIdentity.getIdentity("Servercerts")!!
    }

    @Throws(
        IOException::class,
        UnrecoverableEntryException::class,
        CertificateException::class,
        KeyStoreException::class,
        NoSuchAlgorithmException::class,
        CouchbaseLiteException::class
    )
    override fun getClientCertsIdentity(): TLSIdentity {
        val pass = "123456".toCharArray()
        getAsset("client.p12").use { clientCert ->
            KeyStoreUtils.importEntry(
                "PKCS12",
                clientCert,
                pass,
                "testkit",
                pass,
                "ClientCertsSelfsigned"
            )
        }
        return TLSIdentity.getIdentity("ClientCertsSelfsigned")!!
    }
}
