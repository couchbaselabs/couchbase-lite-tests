package com.couchbase.lite.testserver

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.tooling.preview.Preview
import com.couchbase.lite.testserver.ui.theme.TestServerTheme
import com.couchbase.lite.testserver.util.AssetUtil
import java.io.File

class MainActivity : ComponentActivity() {
    var server: TestServer? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        val tempDir = File(filesDir, "CBLTemp")
        tempDir.mkdirs()

        val assetsDir = filesDir.path + "/assets"
        AssetUtil.copyAssets(assets, assetsDir, true)

        TestServer.initFilesContext(filesDir.path, tempDir.path, assetsDir)

        server = TestServer()
        server?.start()

        setContent {
            TestServerTheme {
                // A surface container using the 'background' color from the theme
                Surface(modifier = Modifier.fillMaxSize(), color = MaterialTheme.colorScheme.background) {
                    Greeting("CBL-C Test Server")
                }
            }
        }
    }

    override fun onDestroy() {
        super.onDestroy()
        server?.stop()
    }
}

@Composable
fun Greeting(name: String, modifier: Modifier = Modifier) {
    Text(
            text = "$name!",
            modifier = modifier
    )
}

@Preview(showBackground = true)
@Composable
fun GreetingPreview() {
    TestServerTheme {
        Greeting("Android")
    }
}