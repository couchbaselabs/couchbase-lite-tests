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
package com.couchbase.lite.mobiletest.changes;

import androidx.annotation.NonNull;
import androidx.annotation.Nullable;

import java.io.File;
import java.io.IOException;
import java.io.InputStream;
import java.util.List;
import java.util.Map;

import edu.umd.cs.findbugs.annotations.SuppressFBWarnings;

import com.couchbase.lite.Blob;
import com.couchbase.lite.Collection;
import com.couchbase.lite.CouchbaseLiteException;
import com.couchbase.lite.Document;
import com.couchbase.lite.MutableDocument;
import com.couchbase.lite.mobiletest.TestApp;
import com.couchbase.lite.mobiletest.endpoints.v1.Session;
import com.couchbase.lite.mobiletest.errors.CblApiFailure;
import com.couchbase.lite.mobiletest.errors.ClientError;
import com.couchbase.lite.mobiletest.errors.ServerError;
import com.couchbase.lite.mobiletest.services.DatabaseService;
import com.couchbase.lite.mobiletest.services.Log;
import com.couchbase.lite.mobiletest.util.FileUtils;
import com.couchbase.lite.mobiletest.util.NetUtils;
import com.couchbase.lite.mobiletest.util.StringUtils;


@SuppressFBWarnings("EI_EXPOSE_REP2")
public final class UpdateChange extends Change {
    private static final String TAG = "DB_UDATE";

    private static final String BLOB_DIR = "blobs/";

    private static final String EXT_JPEG = ".jpg";
    private static final String MIME_JPEG = "image/jpeg";
    private static final String MIME_OCTET = "application/octet-stream";

    @NonNull
    private final List<String> deletions;
    @NonNull
    private final Map<String, Object> updates;
    @NonNull
    private final Map<String, String> blobs;

    public UpdateChange(
        @NonNull String docId,
        @NonNull List<String> deletions,
        @NonNull Map<String, Object> updates,
        @NonNull Map<String, String> blobs) {
        super(ChangeType.UPDATE, docId);
        this.deletions = deletions;
        this.updates = updates;
        this.blobs = blobs;
    }


    @Override
    @NonNull
    public MutableDocument applyChange(@NonNull Collection collection, @Nullable Document doc) {
        final KeypathParser parser = new KeypathParser();

        final MutableDocument mDoc = (doc != null) ? doc.toMutable() : new MutableDocument(docId);
        final Map<String, Object> data = mDoc.toMap();

        for (String deletion: deletions) { parser.parse(deletion).delete(data); }

        for (Map.Entry<String, Object> change: updates.entrySet()) {
            parser.parse(change.getKey()).set(data, change.getValue());
        }

        if (!blobs.isEmpty()) {
            for (Map.Entry<String, String> blob: blobs.entrySet()) {
                final String content = blob.getValue();
                parser.parse(blob.getKey()).set(data, getBlob(content));
            }
        }

        return mDoc.setData(data);
    }

    @Override
    public void updateDocument(@NonNull DatabaseService dbSvc, @NonNull Collection collection) {
        final Document doc = dbSvc.getDocOrNull(collection, docId);
        try { collection.save(applyChange(collection, doc)); }
        catch (CouchbaseLiteException e) { throw new CblApiFailure("Failed saving updated document", e); }
    }

    // Support blobs specified either as a URI or as a blob name and blobs that are either zipped or not.
    // Assume:
    // if the blob is specified as a URI, the name of the blob file is the last thing in the URI path
    // if the blob is zipped, the name of the blob is just the blob file name without the .zip extension
    @SuppressWarnings("PMD.NPathComplexity")
    @NonNull
    private Blob getBlob(@NonNull String content) {
        final Session session = TestApp.getApp().getSession();
        if (session == null) { throw new ClientError("Attempt to resolve blob content with no session"); }

        final FileUtils fileUtils = new FileUtils();
        final File tmpDir = session.getTmpDir();
        final boolean isUri = NetUtils.isURI(content);

        // If the blob file is sitting there and we just need to add it.
        // If it isn't we need to download it and, if the download is zipped, we need to unzip it.
        String blobFileName = (!isUri) ? content : NetUtils.getFileFromURI(content);
        File blobFile = new File(tmpDir, blobFileName);
        if (!blobFile.exists()) {
            final String blobUri = (isUri) ? content : BLOB_DIR + content;
            Log.p(TAG, "Fetching blob: " + blobUri + " to " + blobFile);
            try { NetUtils.fetchFile(blobUri, blobFile); }
            catch (IOException e) { throw new ServerError("Failed fetching blob: " + blobUri, e); }

            if (blobFileName.endsWith(FileUtils.ZIP_EXTENSION)) {
                final File zipFile = blobFile;

                blobFileName = StringUtils.stripSuffix(blobFileName, FileUtils.ZIP_EXTENSION);
                blobFile = new File(tmpDir, blobFileName);
                try (InputStream in = fileUtils.asStream(zipFile)) { fileUtils.unzip(zipFile, blobFile); }
                catch (IOException e) { throw new ServerError("Failed unzipping blob: " + blobFileName, e); }

                // delete the empty husk
                if (!zipFile.delete()) { Log.p(TAG, "Failed deleting blob zipfile: " + zipFile); }
            }
        }

        try { return new Blob(blobFileName.endsWith(EXT_JPEG) ? MIME_JPEG : MIME_OCTET, fileUtils.asStream(blobFile)); }
        catch (IOException e) { throw new ServerError("Failed creating blob from file: " + blobFile, e); }
    }
}
