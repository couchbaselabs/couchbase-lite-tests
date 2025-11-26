import platform
import subprocess
import tempfile
import time
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
from couchbase.management.options import CreatePrimaryQueryIndexOptions
from couchbase.options import ClusterOptions
from couchbase.subdocument import upsert
from opentelemetry.trace import get_tracer

from cbltest.api.error import CblTestError
from cbltest.logging import cbl_warning
from cbltest.utils import _try_n_times
from cbltest.version import VERSION


class CouchbaseServer:
    """
    A class that interacts with a Couchbase Server cluster
    """

    @staticmethod
    def ensure_cluster_healthy(cbs_servers: list["CouchbaseServer"]) -> None:
        """Ensures all CBS nodes are in the cluster and healthy."""
        if len(cbs_servers) < 2:
            return

        cbs_one = cbs_servers[0]
        session = requests.Session()
        session.auth = ("Administrator", "password")

        try:
            resp = session.get(f"http://{cbs_one.hostname}:8091/pools/default")
            resp.raise_for_status()
            cluster_data = resp.json()
        except Exception as e:
            raise CblTestError(f"Cannot connect to CBS cluster: {e}")

        nodes_in_cluster = cluster_data.get("nodes", [])

        for cbs_node in cbs_servers:
            node_in_cluster = False
            node_needs_recovery = False

            for cluster_node in nodes_in_cluster:
                hostname = cluster_node.get("hostname", "").split(":")[0]
                alt_hostname = (
                    cluster_node.get("alternateAddresses", {})
                    .get("external", {})
                    .get("hostname", "")
                )

                if cbs_node.hostname in [hostname, alt_hostname]:
                    node_in_cluster = True
                    if cluster_node.get("clusterMembership") == "inactiveFailed":
                        node_needs_recovery = True
                    break

            if node_needs_recovery:
                cbs_one.recover(cbs_node)
                cbs_one.rebalance_in(cbs_node)
                time.sleep(5)
            elif not node_in_cluster:
                cbs_one.add_node(cbs_node)
                cbs_one.rebalance_in(cbs_node)
                time.sleep(5)

        if not cbs_one.wait_for_cluster_healthy(timeout=120):
            raise CblTestError("CBS cluster did not become healthy")

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

            try:
                self.__cluster = Cluster(url, opts)
                self.__cluster.wait_until_ready(timedelta(seconds=10))
            except Exception:
                self.__cluster = None

    @property
    def hostname(self) -> str:
        """
        Gets the hostname of this Couchbase Server instance.

        :return: The hostname
        """
        return self.__hostname

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
                            c.create_collection(scope_name=scope, collection_name=name)
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

    def create_bucket(self, name: str, num_replicas: int = 0):
        """
        Creates a bucket with a given name that Sync Gateway can use

        :param name: The name of the bucket to create
        :param num_replicas: The number of replicas for the bucket (default 0)
        """
        with self.__tracer.start_as_current_span(
            "create_bucket", attributes={"cbl.bucket.name": name}
        ):
            mgr = self.__cluster.buckets()
            settings = CreateBucketSettings(
                name=name,
                flush_enabled=True,
                ram_quota_mb=512,
                num_replicas=num_replicas,
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

    def delete_document(
        self,
        bucket: str,
        doc_id: str,
        scope: str = "_default",
        collection: str = "_default",
    ) -> None:
        """
        Deletes a document from the specified bucket.scope.collection.
        """
        with self.__tracer.start_as_current_span(
            "delete_document",
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
                coll.remove(doc_id)
            except DocumentNotFoundException:
                pass
            except Exception as e:
                raise CblTestError(
                    f"Failed to delete document '{doc_id}' from {bucket}.{scope}.{collection}: {e}"
                )

    def get_document(
        self,
        bucket: str,
        doc_id: str,
        scope: str = "_default",
        collection: str = "_default",
    ) -> dict | None:
        """
        Gets a document from the specified bucket.scope.collection.

        :param bucket: The bucket name.
        :param doc_id: The document ID.
        :param scope: The scope name.
        :param collection: The collection name.
        :return: The document content as a dictionary, or None if not found.
        """
        with self.__tracer.start_as_current_span(
            "get_document",
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
                result = coll.get(doc_id)
                return result.content_as[dict] if result else None
            except DocumentNotFoundException:
                return None
            except Exception as e:
                raise CblTestError(
                    f"Failed to get document '{doc_id}' from {bucket}.{scope}.{collection}: {e}"
                )

    def upsert_document_xattr(
        self,
        bucket: str,
        doc_id: str,
        xattr_key: str,
        xattr_value: str,
        scope: str = "_default",
        collection: str = "_default",
    ) -> None:
        """
        Upserts an xattr on a document using subdocument operations

        :param bucket: The bucket containing the document
        :param doc_id: The ID of the document to update
        :param xattr_key: The xattr key to upsert
        :param xattr_value: The value to set for the xattr
        :param scope: The scope containing the document (default '_default')
        :param collection: The collection containing the document (default '_default')
        """
        with self.__tracer.start_as_current_span(
            "upsert_document_xattr",
            attributes={
                "cbl.bucket": bucket,
                "cbl.scope": scope,
                "cbl.collection": collection,
                "cbl.document.id": doc_id,
                "cbl.xattr.key": xattr_key,
            },
        ):
            try:
                col = self.__cluster.bucket(bucket).scope(scope).collection(collection)
                col.mutate_in(
                    doc_id,
                    [upsert(xattr_key, xattr_value, xattr=True, create_parents=True)],
                )
            except Exception as e:
                raise CblTestError(
                    f"Failed to upsert xattr '{xattr_key}' on document '{doc_id}' in {bucket}.{scope}.{collection}: {e}"
                )

    def delete_document_xattr(
        self,
        bucket: str,
        doc_id: str,
        xattr_key: str,
        scope: str = "_default",
        collection: str = "_default",
    ) -> None:
        """
        Deletes an xattr from a document using subdocument operations

        :param bucket: The bucket containing the document
        :param doc_id: The ID of the document
        :param xattr_key: The xattr key to delete
        :param scope: The scope containing the document (default '_default')
        :param collection: The collection containing the document (default '_default')
        """
        with self.__tracer.start_as_current_span(
            "delete_document_xattr",
            attributes={
                "cbl.bucket": bucket,
                "cbl.scope": scope,
                "cbl.collection": collection,
                "cbl.document.id": doc_id,
                "cbl.xattr.key": xattr_key,
            },
        ):
            try:
                from couchbase.subdocument import remove

                col = self.__cluster.bucket(bucket).scope(scope).collection(collection)
                col.mutate_in(
                    doc_id,
                    [remove(xattr_key, xattr=True)],
                )
            except Exception:
                pass

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
                            "mobile": "active",
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

    def add_node(
        self,
        node_to_add: "CouchbaseServer",
        services: list[str] | None = None,
    ) -> None:
        """
        Adds a node to the cluster.

        :param node_to_add: The CouchbaseServer instance representing the node to add
        :param services: List of services to enable on the node (e.g. ["kv", "index", "n1ql"])
                        Defaults to ["kv", "index", "n1ql"] (data, index, query)
        """
        if services is None:
            services = ["kv", "index", "n1ql"]

        with self.__tracer.start_as_current_span(
            "add_node",
            attributes={
                "cbl.cluster.hostname": self.__hostname,
                "cbl.node.hostname": node_to_add.__hostname,
            },
        ):
            with requests.Session() as session:
                session.auth = (self.__username, self.__password)

                hostname_to_use = node_to_add.__hostname
                for attempt in range(3):
                    try:
                        node_session = requests.Session()
                        node_session.auth = ("Administrator", "password")
                        node_resp = node_session.get(
                            f"http://{node_to_add.__hostname}:8091/nodes/self",
                            timeout=5,
                        )
                        if node_resp.status_code == 200:
                            internal_hostname = (
                                node_resp.json().get("hostname", "").split(":")[0]
                            )
                            if internal_hostname and not internal_hostname.startswith(
                                "127."
                            ):
                                hostname_to_use = internal_hostname
                                break
                    except Exception:
                        if attempt < 2:
                            time.sleep(5)

                for attempt in range(5):
                    resp = session.post(
                        f"http://{self.__hostname}:8091/controller/addNode",
                        data={
                            "hostname": hostname_to_use,
                            "user": "Administrator",
                            "password": "password",
                            "services": ",".join(services),
                        },
                    )
                    if resp.status_code == 200:
                        break
                    elif attempt < 4:
                        time.sleep(1)
                    else:
                        raise CblTestError(
                            f"Failed to add node {node_to_add.__hostname}: {resp.text}"
                        )

                if hostname_to_use != node_to_add.__hostname:
                    try:
                        session.put(
                            f"http://{node_to_add.__hostname}:8091/node/controller/setupAlternateAddresses/external",
                            data={"hostname": node_to_add.__hostname, "mgmt": "8091"},
                        ).raise_for_status()
                    except Exception:
                        pass

    def rebalance_out(self, node_to_remove: "CouchbaseServer") -> None:
        """
        Rebalances a node out of the cluster (removes it).

        :param node_to_remove: The node to remove from the cluster
        """
        with self.__tracer.start_as_current_span(
            "rebalance_out",
            attributes={
                "cbl.cluster.hostname": self.__hostname,
                "cbl.node.hostname": node_to_remove.__hostname,
            },
        ):
            with requests.Session() as session:
                session.auth = (self.__username, self.__password)

                # Get all node OTP IDs
                resp = session.get(f"http://{self.__hostname}:8091/pools/default")
                resp.raise_for_status()
                pool_data = resp.json()

                # Find the OTP node ID for the node to remove
                ejected_node = None
                known_nodes = []
                for node in pool_data.get("nodes", []):
                    hostname = node.get("hostname", "").split(":")[0]
                    otp_node = node.get("otpNode")
                    known_nodes.append(otp_node)

                    # Check both regular hostname and alternate address
                    if hostname == node_to_remove.__hostname:
                        ejected_node = otp_node
                    else:
                        # Check alternate addresses
                        alt_addrs = node.get("alternateAddresses", {}).get(
                            "external", {}
                        )
                        alt_hostname = alt_addrs.get("hostname", "")
                        if alt_hostname == node_to_remove.__hostname:
                            ejected_node = otp_node

                if ejected_node is None:
                    raise CblTestError(
                        f"Node {node_to_remove.__hostname} not found in cluster. "
                        f"Available nodes: {[n.get('hostname') for n in pool_data.get('nodes', [])]}"
                    )

                # Start rebalance with the node ejected
                resp = session.post(
                    f"http://{self.__hostname}:8091/controller/rebalance",
                    data={
                        "knownNodes": ",".join(known_nodes),
                        "ejectedNodes": ejected_node,
                    },
                )
                resp.raise_for_status()

                # Wait for rebalance to complete
                self._wait_for_rebalance_completion(session)

    def rebalance(self, eject_failed_nodes: bool = False) -> None:
        """
        Rebalances the cluster in its current state.
        Useful after failover to activate replica vBuckets.

        :param eject_failed_nodes: If True, removes failed nodes from cluster.
                                   If False, keeps them for later recovery.
        """
        with self.__tracer.start_as_current_span(
            "rebalance",
            attributes={"cbl.cluster.hostname": self.__hostname},
        ):
            with requests.Session() as session:
                session.auth = (self.__username, self.__password)

                # Get all node OTP IDs
                resp = session.get(f"http://{self.__hostname}:8091/pools/default")
                resp.raise_for_status()
                pool_data = resp.json()

                known_nodes = []
                ejected_nodes = []

                for node in pool_data.get("nodes", []):
                    otp_node = node.get("otpNode")
                    cluster_membership = node.get("clusterMembership")

                    # knownNodes must include ALL nodes (even failed ones)
                    known_nodes.append(otp_node)

                    # Only eject if explicitly requested
                    if eject_failed_nodes and cluster_membership == "inactiveFailed":
                        ejected_nodes.append(otp_node)

                # Start rebalance
                rebalance_data = {"knownNodes": ",".join(known_nodes)}
                if ejected_nodes:
                    rebalance_data["ejectedNodes"] = ",".join(ejected_nodes)

                resp = session.post(
                    f"http://{self.__hostname}:8091/controller/rebalance",
                    data=rebalance_data,
                )

                if not resp.ok:
                    error_msg = f"Rebalance failed: {resp.status_code} - {resp.text}"
                    raise CblTestError(error_msg)

                resp.raise_for_status()

                # Wait for rebalance to complete
                self._wait_for_rebalance_completion(session)

    def rebalance_in(self, node_to_add: "CouchbaseServer") -> None:
        """
        Rebalances a node into the cluster (completes adding it).

        :param node_to_add: The node that was added and needs rebalancing
        """
        with self.__tracer.start_as_current_span(
            "rebalance_in",
            attributes={
                "cbl.cluster.hostname": self.__hostname,
                "cbl.node.hostname": node_to_add.__hostname,
            },
        ):
            with requests.Session() as session:
                session.auth = (self.__username, self.__password)

                # Get all node OTP IDs
                resp = session.get(f"http://{self.__hostname}:8091/pools/default")
                resp.raise_for_status()
                pool_data = resp.json()

                known_nodes = [
                    node.get("otpNode") for node in pool_data.get("nodes", [])
                ]

                # Start rebalance with retry
                for attempt in range(5):
                    try:
                        resp = session.post(
                            f"http://{self.__hostname}:8091/controller/rebalance",
                            data={"knownNodes": ",".join(known_nodes)},
                        )
                        resp.raise_for_status()
                        break
                    except Exception:
                        if attempt < 4:
                            time.sleep(1)
                        else:
                            raise

                # Wait for rebalance to complete
                self._wait_for_rebalance_completion(session)

    def failover(self, node_to_failover: "CouchbaseServer") -> None:
        """
        Performs a hard failover on a node in the cluster (simulates sudden node failure).

        :param node_to_failover: The node to failover
        """
        with self.__tracer.start_as_current_span(
            "failover",
            attributes={
                "cbl.cluster.hostname": self.__hostname,
                "cbl.node.hostname": node_to_failover.__hostname,
            },
        ):
            with requests.Session() as session:
                session.auth = (self.__username, self.__password)

                # Get all node OTP IDs
                resp = session.get(f"http://{self.__hostname}:8091/pools/default")
                resp.raise_for_status()
                pool_data = resp.json()

                # Find the OTP node ID for the node to failover
                failover_node = None
                for node in pool_data.get("nodes", []):
                    hostname = node.get("hostname", "").split(":")[0]
                    otp_node = node.get("otpNode")

                    # Check both regular hostname and alternate address
                    if hostname == node_to_failover.__hostname:
                        failover_node = otp_node
                        break
                    else:
                        alt_addrs = node.get("alternateAddresses", {}).get(
                            "external", {}
                        )
                        alt_hostname = alt_addrs.get("hostname", "")
                        if alt_hostname == node_to_failover.__hostname:
                            failover_node = otp_node
                            break

                if failover_node is None:
                    raise CblTestError(
                        f"Node {node_to_failover.__hostname} not found in cluster for failover"
                    )

                # Perform hard failover
                resp = session.post(
                    f"http://{self.__hostname}:8091/controller/failOver",
                    data={"otpNode": failover_node},
                )
                resp.raise_for_status()

    def recover(self, node_to_recover: "CouchbaseServer") -> None:
        """
        Recovers a failed node and sets it to full recovery mode.

        :param node_to_recover: The node to recover
        """
        with self.__tracer.start_as_current_span(
            "recover",
            attributes={
                "cbl.cluster.hostname": self.__hostname,
                "cbl.node.hostname": node_to_recover.__hostname,
            },
        ):
            with requests.Session() as session:
                session.auth = (self.__username, self.__password)

                # Get all node OTP IDs
                resp = session.get(f"http://{self.__hostname}:8091/pools/default")
                resp.raise_for_status()
                pool_data = resp.json()

                # Find the OTP node ID for the node to recover
                recovery_node = None
                for node in pool_data.get("nodes", []):
                    hostname = node.get("hostname", "").split(":")[0]
                    otp_node = node.get("otpNode")

                    # Check both regular hostname and alternate address
                    if hostname == node_to_recover.__hostname:
                        recovery_node = otp_node
                        break
                    else:
                        alt_addrs = node.get("alternateAddresses", {}).get(
                            "external", {}
                        )
                        alt_hostname = alt_addrs.get("hostname", "")
                        if alt_hostname == node_to_recover.__hostname:
                            recovery_node = otp_node
                            break

                if recovery_node is None:
                    raise CblTestError(
                        f"Node {node_to_recover.__hostname} not found in cluster for recovery"
                    )

                # Set recovery type to delta (faster than full recovery)
                resp = session.post(
                    f"http://{self.__hostname}:8091/controller/setRecoveryType",
                    data={"otpNode": recovery_node, "recoveryType": "delta"},
                )
                resp.raise_for_status()

    def wait_for_cluster_healthy(
        self, timeout: int = 60, check_interval: int = 2
    ) -> bool:
        """
        Waits for the cluster to become healthy after a failover or rebalance operation.
        Checks that all active nodes are healthy and vBuckets are available.

        :param timeout: Maximum time to wait in seconds (default: 60)
        :param check_interval: Time between health checks in seconds (default: 2)
        :return: True if cluster is healthy, False if timeout reached
        """
        with self.__tracer.start_as_current_span(
            "wait_for_cluster_healthy",
            attributes={"cbl.cluster.hostname": self.__hostname},
        ):
            start_time = time.time()

            while (time.time() - start_time) < timeout:
                try:
                    with requests.Session() as session:
                        session.auth = (self.__username, self.__password)

                        # Check cluster status
                        resp = session.get(
                            f"http://{self.__hostname}:8091/pools/default"
                        )
                        resp.raise_for_status()
                        pool_data = resp.json()

                        # Check rebalance status
                        if pool_data.get("rebalanceStatus", "none") != "none":
                            time.sleep(check_interval)
                            continue

                        # Check active nodes are healthy
                        all_healthy = all(
                            node.get("status") == "healthy"
                            for node in pool_data.get("nodes", [])
                            if node.get("clusterMembership") == "active"
                        )

                        if not all_healthy:
                            time.sleep(check_interval)
                            continue

                        # Check bucket vBuckets
                        buckets_resp = session.get(
                            f"http://{self.__hostname}:8091/pools/default/buckets"
                        )
                        buckets_resp.raise_for_status()

                        all_buckets_healthy = True
                        for bucket in buckets_resp.json():
                            vbucket_map = bucket.get("vBucketServerMap", {})
                            if not vbucket_map.get("serverList") or not vbucket_map.get(
                                "vBucketMap"
                            ):
                                all_buckets_healthy = False
                                break

                            # Check all vBuckets have active nodes
                            if any(
                                not vb or vb[0] == -1
                                for vb in vbucket_map.get("vBucketMap", [])
                            ):
                                all_buckets_healthy = False
                                break

                        if not all_buckets_healthy:
                            time.sleep(check_interval)
                            continue

                        return True

                except Exception:
                    time.sleep(check_interval)

            return False

    def _wait_for_rebalance_completion(
        self, session: requests.Session, timeout_seconds: int = 300
    ) -> None:
        """
        Waits for a rebalance operation to complete.

        :param session: The requests session to use
        :param timeout_seconds: Maximum time to wait (default 300 seconds / 5 minutes)
        """
        start_time = time.time()
        while time.time() - start_time < timeout_seconds:
            resp = session.get(
                f"http://{self.__hostname}:8091/pools/default/rebalanceProgress"
            )
            resp.raise_for_status()
            status = resp.json()

            if status.get("status") == "none":
                # Rebalance completed
                return

            sleep(2)

        raise CblTestError(
            f"Rebalance did not complete within {timeout_seconds} seconds"
        )
