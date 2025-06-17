import platform
import subprocess
import tempfile
import zipfile
from datetime import timedelta
from pathlib import Path
from time import sleep
from typing import cast
from urllib.parse import quote_plus, urlparse

import requests
from couchbase.auth import PasswordAuthenticator
from couchbase.cluster import Cluster
from couchbase.exceptions import (
    BucketAlreadyExistsException,
    BucketDoesNotExistException,
    CollectionAlreadyExistsException,
    DocumentNotFoundException,
    QueryIndexAlreadyExistsException,
    ScopeAlreadyExistsException,
)
from couchbase.management.buckets import CreateBucketSettings
from couchbase.management.collections import CollectionSpec
from couchbase.management.options import CreatePrimaryQueryIndexOptions
from couchbase.options import ClusterOptions
from opentelemetry.trace import get_tracer

from cbltest.api.error import CblTestError
from cbltest.logging import cbl_warning
from cbltest.utils import _try_n_times
from cbltest.version import VERSION


class CouchbaseServer:
    """
    A class that interacts with a Couchbase Server cluster
    """

    def __init__(self, url: str, username: str, password: str):
        self.__tracer = get_tracer(__name__, VERSION)
        with self.__tracer.start_as_current_span("connect_to_couchbase_server"):
            if "://" not in url:
                url = f"couchbase://{url}"

            self.__hostname = (
                urlparse(url).hostname or urlparse(url).netloc.split(":")[0]
            )
            auth = PasswordAuthenticator(username, password)
            opts = ClusterOptions(auth)
            self.__username = username
            self.__password = password
            self.__cluster = Cluster(url, opts)
            self.__cluster.wait_until_ready(timedelta(seconds=10))

    def create_collections(self, bucket: str, scope: str, names: list[str]) -> None:
        """
        A function that will create a specified set of collections in the specified scope
        which resides in the specified bucket

        :param bucket: The bucket name in which the scope resides
        :param scope: The scope in which to create the collections.  It will be created
                      if it doesn't already exist, unless it is the default scope
        :param names: The names of the collections to create
        """
        with self.__tracer.start_as_current_span(
            "Create Scope",
            attributes={"cbl.scope.name": scope, "cbl.bucket.name": bucket},
        ):
            bucket_obj = _try_n_times(10, 1, False, self.__cluster.bucket, bucket)
            c = bucket_obj.collections()
            try:
                if scope != "_default":
                    c.create_scope(scope)
            except ScopeAlreadyExistsException:
                pass

            for name in names:
                with self.__tracer.start_as_current_span(
                    "Create Collection",
                    attributes={
                        "cbl.scope.name": scope,
                        "cbl.bucket.name": bucket,
                        "cbl.collection.name": name,
                    },
                ):
                    try:
                        if name != "_default":
                            c.create_collection(CollectionSpec(name, scope))
                    except CollectionAlreadyExistsException:
                        pass

                success = False
                for _ in range(0, 10):
                    try:
                        bucket_obj.scope(scope).collection(name).get("_nonexistent")
                    except DocumentNotFoundException:
                        success = True
                        break
                    except Exception:
                        cbl_warning(
                            f"{bucket}.{scope}.{name} appears to not be ready yet, waiting for 1 second..."
                        )
                        sleep(1.0)

                if not success:
                    raise CblTestError(
                        f"Unable to properly create {bucket}.{scope}.{name} in Couchbase Server"
                    )

    def create_bucket(self, name: str):
        """
        Creates a bucket with a given name that Sync Gateway can use

        :param name: The name of the bucket to create
        """
        with self.__tracer.start_as_current_span(
            "create_bucket", attributes={"cbl.bucket.name": name}
        ):
            mgr = self.__cluster.buckets()
            settings = CreateBucketSettings(
                name=name, flush_enabled=True, ram_quota_mb=512
            )
            try:
                mgr.create_bucket(settings)
            except BucketAlreadyExistsException:
                pass

    def drop_bucket(self, name: str):
        """
        Drops a bucket from the Couchbase cluster

        :param name: The name of the bucket to drop
        """
        with self.__tracer.start_as_current_span(
            "drop_bucket", attributes={"cbl.bucket.name": name}
        ):
            try:
                mgr = self.__cluster.buckets()
                mgr.drop_bucket(name)
            except BucketDoesNotExistException:
                pass

    def restore_bucket(
        self,
        name: str,
        tools_path: Path,
        dataset_path: Path,
        dataset_name: str,
        *,
        tools_version: str = "7.6.7",
        repo_name: str | None = None,
    ) -> None:
        """
        Restores a bucket from a backup source

        :param name: The name of the bucket to restore
        :param backup_source: The path to the backup source
        """
        with self.__tracer.start_as_current_span(
            "restore_bucket",
            attributes={"cbl.bucket.name": name, "cbl.backup.source": dataset_name},
        ):
            bin_name = (
                "cbbackupmgr.exe" if platform.system() == "Windows" else "cbbackupmgr"
            )
            cbbackupmgr_path = tools_path / "cbbackupmgr" / tools_version / bin_name
            if not cbbackupmgr_path.exists():
                raise FileNotFoundError(
                    "cbbackupmgr not found, please download it with the environment/aws/download_tool script"
                )

            # For historical reasons, dataset_path is pointing to the Sync Gateway dataset
            # directory.  This should be changed in the future, but for now to avoid breakage
            # just find the neighboring couchbase-server directory.
            data_filepath = (
                dataset_path / ".." / "couchbase-server" / f"{dataset_name}.zip"
            )
            if not data_filepath.exists():
                raise FileNotFoundError(f"Data file {dataset_name}.zip not found!")

            with tempfile.TemporaryDirectory(prefix="cbl_backup_") as tmpdir:
                extract_path = Path(tmpdir)
                try:
                    with zipfile.ZipFile(data_filepath, "r") as zf:
                        zf.extractall(extract_path)
                except zipfile.BadZipFile as e:
                    raise CblTestError(
                        f"Backup zip '{data_filepath}' is invalid: {e}"
                    ) from e

                subprocess.run(
                    [
                        cbbackupmgr_path,
                        "restore",
                        "-a",
                        str(extract_path / dataset_name),
                        "-c",
                        self.__hostname,
                        "-r",
                        repo_name or dataset_name,
                        "-u",
                        self.__username,
                        "-p",
                        self.__password,
                        "--auto-create-buckets",
                    ],
                    check=True,
                )

    def indexes_count(self, bucket: str) -> int:
        """
        Returns the number of indexes that are in the specified bucket

        :param bucket: The bucket to check for indexes
        """
        with self.__tracer.start_as_current_span(
            "indexes_count", attributes={"cbl.bucket.name": bucket}
        ):
            index_mgr = self.__cluster.query_indexes()
            indexes = list(index_mgr.get_all_indexes(bucket))
            return len(indexes)

    def run_query(
        self,
        query: str,
        bucket: str,
        scope: str = "_default",
        collection: str = "_default",
    ) -> list[dict]:
        """
        Runs the specified query on the server.  The query may be formatted in a special way.

        :param query: The SQL++ query to run
        :param bucket: The bucket that the data to query is located in
        :param scope: The scope that the data to query is located in
        :param collection: The collection that the data to query is located in

        .. note::
            The FROM clause of this query can be a python substitution string ({}).  If
            it is, the FROM clause will be replaced with the proper bucket.scope.collection
            format at execution time.
        """
        actual_query = query.format(f"{bucket}.{scope}.{collection}")
        with self.__tracer.start_as_current_span(
            "run_query", attributes={"cbl.query.name": actual_query}
        ):
            query_obj = self.__cluster.query(actual_query)
            try:
                self.__cluster.query_indexes().create_primary_index(
                    bucket,
                    CreatePrimaryQueryIndexOptions(
                        scope_name=scope, collection_name=collection
                    ),
                )
            except QueryIndexAlreadyExistsException:
                pass

            return list(dict(result) for result in query_obj.execute())

    def upsert_document(
        self,
        bucket: str,
        doc_id: str,
        document: dict,
        scope: str = "_default",
        collection: str = "_default",
    ) -> None:
        """
        Inserts a document into the specified bucket.scope.collection.

        :param bucket: The bucket name.
        :param scope: The scope name.
        :param collection: The collection name.
        :param doc_id: The document ID.
        :param document: The document content (a dictionary).
        """
        with self.__tracer.start_as_current_span(
            "insert_document",
            attributes={
                "cbl.bucket.name": bucket,
                "cbl.scope.name": scope,
                "cbl.collection.name": collection,
                "cbl.document.id": doc_id,
            },
        ):
            try:
                bucket_obj = _try_n_times(10, 1, False, self.__cluster.bucket, bucket)
                coll = bucket_obj.scope(scope).collection(collection)
                coll.upsert(doc_id, document)
            except Exception as e:
                raise CblTestError(
                    f"Failed to insert document '{doc_id}' into {bucket}.{scope}.{collection}: {e}"
                )

    def start_xdcr(self, target: "CouchbaseServer", bucket_name: str) -> None:
        """
        Starts an XDCR replication from this cluster to the target cluster

        :param target: The target CouchbaseServer instance to replicate to
        :param source_bucket: The bucket on this cluster to replicate from
        :param target_bucket: The bucket on the target cluster to replicate to
        """
        with self.__tracer.start_as_current_span(
            "start_xdcr",
            attributes={
                "cbl.bucket": bucket_name,
                "cbl.target.hostname": target.__hostname,
            },
        ):
            with requests.Session() as session:
                session.auth = (self.__username, self.__password)

                # Get the existing remote cluster, if any...
                resp = session.get(
                    f"http://{self.__hostname}:8091/pools/default/remoteClusters"
                )
                resp.raise_for_status()
                resp_body = resp.json()
                remote_cluster_uuid: str | None = None
                for cluster in resp_body:
                    if (
                        "name" in cluster
                        and cast(str, cluster["name"]) == target.__hostname
                    ):
                        remote_cluster_uuid = cluster["uuid"]
                        break

                # https://docs.couchbase.com/server/current/learn/clusters-and-availability/xdcr-active-active-sgw.html#xdcr-active-active-sgw-prerequisites
                # Set the prerequisite properties.  These return 409 is they are already set.
                resp = session.post(
                    f"http://{self.__hostname}:8091/pools/default/buckets/{bucket_name}",
                    data={"enableCrossClusterVersioning": "true"},
                )
                if resp.status_code != 409:
                    resp.raise_for_status()

                resp = session.post(
                    f"http://{target.__hostname}:8091/pools/default/buckets/{bucket_name}",
                    data={"enableCrossClusterVersioning": "true"},
                )
                if resp.status_code != 409:
                    resp.raise_for_status()

                # https://docs.couchbase.com/server/current/manage/manage-xdcr/create-xdcr-replication.html#create-an-xdcr-replication-with-the-rest-api
                # Create the remote cluster, if necessary
                if remote_cluster_uuid is None:
                    resp = session.post(
                        f"http://{self.__hostname}:8091/pools/default/remoteClusters",
                        data={
                            "username": target.__username,
                            "password": target.__password,
                            "hostname": target.__hostname,
                            "name": target.__hostname,
                            "demandEncryption": 0,
                            "mobile": "active",
                        },
                    )
                    resp.raise_for_status()

                needs_replication = True
                if remote_cluster_uuid is not None:
                    # If the remote cluster didn't exist, the replication could not have existed
                    # so skip the lookup.  Otherwise, check for a replication that is already
                    # going out to the remote cluster in question.
                    resp = session.get(
                        f"http://{self.__hostname}:8091/pools/default/tasks"
                    )
                    resp.raise_for_status()
                    for task in resp.json():
                        if "type" in task and task["type"] == "xdcr":
                            if "id" in task:
                                id = task["id"]
                                if (
                                    id
                                    == f"{remote_cluster_uuid}/{bucket_name}/{bucket_name}"
                                ):
                                    needs_replication = False
                                    break

                if needs_replication:
                    resp = session.post(
                        f"http://{self.__hostname}:8091/controller/createReplication",
                        data={
                            "fromBucket": bucket_name,
                            "toCluster": target.__hostname,
                            "toBucket": bucket_name,
                            "replicationType": "continuous",
                            "compressionLevel": "Auto",
                        },
                    )
                    resp.raise_for_status()

    def stop_xcdr(self, target: "CouchbaseServer", bucket_name: str) -> None:
        """
        Stops an XDCR replication from this cluster to the target cluster.  Note
        that this does not remove the remote cluster.

        :param target: The target CouchbaseServer instance to replicate to
        :param source_bucket: The bucket on this cluster to replicate from
        :param target_bucket: The bucket on the target cluster to replicate to
        """
        with self.__tracer.start_as_current_span(
            "stop_xdcr",
            attributes={
                "cbl.bucket": bucket_name,
                "cbl.target.hostname": target.__hostname,
            },
        ):
            with requests.Session() as session:
                session.auth = (self.__username, self.__password)

                # See if the remote cluster already exists
                resp = session.get(
                    f"http://{self.__hostname}:8091/pools/default/remoteClusters"
                )
                resp.raise_for_status()
                resp_body = resp.json()
                remote_cluster_uuid: str | None = None
                for cluster in resp_body:
                    if (
                        "name" in cluster
                        and cast(str, cluster["name"]) == target.__hostname
                    ):
                        remote_cluster_uuid = cluster["uuid"]
                        break

                if remote_cluster_uuid is None:
                    return

                # See if the XDCR already exists
                resp = session.get(f"http://{self.__hostname}:8091/pools/default/tasks")
                resp.raise_for_status()
                xdcr_id: str | None = None
                for task in resp.json():
                    if "type" in task and task["type"] == "xdcr":
                        if "id" in task:
                            id = task["id"]
                            if (
                                id
                                == f"{remote_cluster_uuid}/{bucket_name}/{bucket_name}"
                            ):
                                xdcr_id = id
                                break

                if xdcr_id is not None:
                    encoded = quote_plus(xdcr_id)
                    resp = session.delete(
                        f"http://{self.__hostname}:8091/controller/cancelXDCR/{encoded}",
                    )
                    resp.raise_for_status()
