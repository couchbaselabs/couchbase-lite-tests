package com.couchbase.lite.testserver.util;

import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.io.IOException;
import java.net.HttpURLConnection;
import java.net.URL;

public class FileDownloader {
    public static void download(String url, String destinationPath) throws IOException {
        HttpURLConnection connection = (HttpURLConnection) new URL(url).openConnection();
        connection.setConnectTimeout(60_000);
        connection.setReadTimeout(60_000);
        connection.setRequestMethod("GET");

        int responseCode = connection.getResponseCode();
        if (responseCode != HttpURLConnection.HTTP_OK) {
            throw new IOException("Failed to download file from URL '" + url + "' : " +
                    responseCode + " " + connection.getResponseMessage());
        }

        File file = new File(destinationPath);
        try (InputStream input = connection.getInputStream();
             FileOutputStream output = new FileOutputStream(file)) {
            byte[] buffer = new byte[8192];
            int len;
            while ((len = input.read(buffer)) != -1) {
                output.write(buffer, 0, len);
            }
        } finally {
            connection.disconnect();
        }
    }
}