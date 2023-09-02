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
import android.os.Build
import android.util.Base64
import com.couchbase.lite.CouchbaseLite
import com.couchbase.lite.CouchbaseLiteException
import com.couchbase.lite.Database
import com.couchbase.lite.KeyStoreUtils
import com.couchbase.lite.LogDomain
import com.couchbase.lite.LogLevel
import com.couchbase.lite.TLSIdentity
import com.couchbase.lite.internal.core.CBLVersion
import com.couchbase.lite.mobiletest.TestApp
import java.io.IOException
import java.security.KeyStoreException
import java.security.NoSuchAlgorithmException
import java.security.UnrecoverableEntryException
import java.security.cert.CertificateException
import java.util.*


class AndroidTestApp(private val context: Context) : TestApp() {

    override fun initCBL() {
        CouchbaseLite.init(context, true)
        val logger = Database.log.console
        logger.domains = LogDomain.ALL_DOMAINS
        logger.level = LogLevel.DEBUG
    }

    override fun getPlatform() = "android"

    override fun getSystemInfo(): Map<String, Any> {
        return mapOf(
            KEY_SERVER_VERSION to com.couchbase.lite.BuildConfig.VERSION_NAME,
            KEY_API to LATEST_SUPPORTED_PROTOCOL_VERSION,
            KEY_CBL to "couchbase-lite-android-ee-ktx",
            KEY_DEVICE to mapOf(
                KEY_DEVICE_MODEL to Build.PRODUCT,
                KEY_DEVICE_SYS_NAME to "android",
                KEY_DEVICE_SYS_VERSION to Build.VERSION.RELEASE,
                KEY_DEVICE_SYS_API to Build.VERSION.SDK_INT
            ),
            KEY_ADDITIONAL_INFO
                    to "Android Test Server ${BuildConfig.VERSION_NAME} using ${CBLVersion.getVersionInfo()}"
        )
    }

    override fun getFilesDir() = context.filesDir!!

    @Throws(IOException::class)
    override fun getAsset(name: String)= context.assets.open(name)

    override fun encodeBase64(hashBytes: ByteArray) = Base64.encodeToString(hashBytes, Base64.NO_WRAP)!!

    override fun decodeBase64(encodedBytes: String) = Base64.decode(encodedBytes, Base64.NO_WRAP)!!

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
