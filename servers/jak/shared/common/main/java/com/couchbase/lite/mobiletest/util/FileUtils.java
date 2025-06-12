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

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileNotFoundException;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.util.ArrayList;
import java.util.List;
import java.util.zip.ZipEntry;
import java.util.zip.ZipInputStream;
import java.util.zip.ZipOutputStream;

import com.couchbase.lite.mobiletest.services.Log;


public class FileUtils {
    public static final String ZIP_EXTENSION = ".zip";


    private static final String TAG = "FILE_UTIL";

    private final byte[] buffer = new byte[1024];

    // New stream constructors are supported only in API 26+
    @NonNull
    public FileInputStream asStream(@NonNull File file) throws FileNotFoundException {
        return new FileInputStream(file);
    }

    @NonNull
    public byte[] readToByteArray(@NonNull InputStream in) {
        final ByteArrayOutputStream out = new ByteArrayOutputStream();
        try { copyStream(in, out); }
        catch (IOException err) { Log.err(TAG, "Ignoring exception while copying stream to memory", err); }
        return out.toByteArray();
    }

    @NonNull
    public byte[] readToByteArray(@NonNull File srcFile) throws IOException {
        final ByteArrayOutputStream out = new ByteArrayOutputStream();
        try (FileInputStream in = new FileInputStream(srcFile)) { copyStream(in, out); }
        return out.toByteArray();
    }

    public void copyStream(@NonNull InputStream in, @NonNull OutputStream out) throws IOException {
        int read;
        while ((read = in.read(buffer)) != -1) { out.write(buffer, 0, read); }
    }

    public void moveFileOrDir(@NonNull File src, @NonNull File dst) throws IOException {
        if (!src.exists()) { return; }

        if (dst.exists()) { deleteRecursive(dst); }

        copyFileOrDir(src, dst);

        deleteRecursive(src);
    }

    public boolean deleteRecursive(@NonNull File fileOrDirectory) {
        return (!fileOrDirectory.exists()) || (deleteContents(fileOrDirectory) && fileOrDirectory.delete());
    }

    public void zipDirectory(@NonNull File srcDir, @NonNull File zipFile) throws IOException {
        final List<String> zipFiles = new ArrayList<>();
        addFilesList(srcDir, zipFiles);

        final int prefixLen = srcDir.getAbsolutePath().length() + 1;
        final String srcName = srcDir.getName();
        try (FileOutputStream fos = new FileOutputStream(zipFile); ZipOutputStream zos = new ZipOutputStream(fos)) {
            for (String path: zipFiles) {
                try (FileInputStream fis = new FileInputStream(path)) {
                    zos.putNextEntry(new ZipEntry(srcName + "/" + path.substring(prefixLen)));
                    copyStream(fis, zos);
                }
                finally {
                    try { zos.closeEntry(); } catch (IOException ignore) { }
                }
                Log.p(TAG, "Zipped file " + path);
            }
        }
    }

    public void unzip(@NonNull File src, @NonNull File dest) throws IOException { unzip(asStream(src), dest); }

    public void unzip(@NonNull InputStream src, @NonNull File dest) throws IOException {
        File root = null;
        try (InputStream in = src; ZipInputStream zis = new ZipInputStream(in)) {
            ZipEntry ze = zis.getNextEntry();
            while (ze != null) {
                final File newFile = new File(dest, ze.getName());
                if (root == null) { root = newFile; }
                if (ze.isDirectory()) { mkPath(newFile); }
                else {
                    final String parent = newFile.getParent();
                    if (parent != null) { mkPath(new File(parent)); }
                    try (FileOutputStream fos = new FileOutputStream(newFile)) { copyStream(zis, fos); }
                }
                ze = zis.getNextEntry();
            }
            zis.closeEntry();
        }
        Log.p(TAG, "Unzipped file " + root);
    }

    private void addFilesList(@NonNull File dir, @NonNull List<String> files) {
        final File[] contents = dir.listFiles();
        if (contents == null) { return; }
        for (File file: contents) {
            if (file.isDirectory()) { addFilesList(file, files); }
            else { files.add(file.getAbsolutePath()); }
        }
    }

    private boolean deleteContents(File fileOrDirectory) {
        if ((fileOrDirectory == null) || (!fileOrDirectory.isDirectory())) { return true; }

        final File[] contents = fileOrDirectory.listFiles();
        if (contents == null) { return true; }

        boolean succeeded = true;
        for (File file: contents) {
            if (!deleteRecursive(file)) {
                Log.p(TAG, "Failed deleting file: " + file);
                succeeded = false;
            }
        }

        return succeeded;
    }

    // New stream constructors are supported only in API 26+
    @SuppressWarnings("IOStreamConstructor")
    private void copyFileOrDir(@NonNull File src, @NonNull File dst) throws IOException {
        if (!src.isDirectory()) {
            try (InputStream in = new FileInputStream(src); OutputStream out = new FileOutputStream(dst)) {
                copyStream(in, out);
            }
            Log.p(TAG, "File copied from " + src + " to " + dst);
            return;
        }

        if (!dst.mkdir()) { throw new IOException("Failed creating directory: " + dst); }

        final String[] files = src.list();
        if (files != null) {
            for (String file: files) { copyFileOrDir(new File(src, file), new File(dst, file)); }
        }
        Log.p(TAG, "Directory copied from " + src + "  to " + dst);
    }

    private void mkPath(@NonNull File path) throws IOException {
        if (!(path.exists() || path.mkdirs())) { throw new IOException("Failed to create directory: " + path); }
    }
}



