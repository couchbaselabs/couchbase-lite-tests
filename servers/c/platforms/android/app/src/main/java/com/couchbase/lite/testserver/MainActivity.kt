package com.couchbase.lite.testserver

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.sp
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
                    Title("Test Server for C")
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
fun Title(name: String, modifier: Modifier = Modifier) {
    Box(
        contentAlignment = Alignment.Center
    ) {
        Text(
            text = "$name",
            fontSize = 30.sp,
            textAlign = TextAlign.Center,
            modifier = modifier
        )
    }

}

@Preview(showBackground = true)
@Composable
fun TitlePreview() {
    TestServerTheme {
        Title("Android")
    }
}