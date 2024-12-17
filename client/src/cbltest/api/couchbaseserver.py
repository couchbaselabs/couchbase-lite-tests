from datetime import timedelta
from typing import Dict, List
from opentelemetry.trace import get_tracer
from time import sleep
import requests

from couchbase.bucket import Bucket
from couchbase.cluster import Cluster
from couchbase.options import ClusterOptions
from couchbase.auth import PasswordAuthenticator
from couchbase.management.buckets import CreateBucketSettings
from couchbase.management.collections import CollectionSpec
from couchbase.management.options import CreatePrimaryQueryIndexOptions
from couchbase.exceptions import BucketAlreadyExistsException, BucketDoesNotExistException, ScopeAlreadyExistsException
from couchbase.exceptions import CollectionAlreadyExistsException, QueryIndexAlreadyExistsException, DocumentNotFoundException

from cbltest.utils import _try_n_times
from cbltest.version import VERSION
from cbltest.logging import cbl_warning
from cbltest.api.error import CblTestError

class CouchbaseServer:
    """
    A class that interacts with a Couchbase Server cluster
    """
    def __init__(self, url: str, username: str, password: str):
        self.__tracer = get_tracer(__name__, VERSION)
        with self.__tracer.start_as_current_span("connect_to_couchbase_server"):
            if "://" not in url:
                url = f"couchbase://{url}"

            auth = PasswordAuthenticator(username, password)
            opts = ClusterOptions(auth)
            self.__cluster = Cluster(url, opts)
            self.__cluster.wait_until_ready(timedelta(seconds=10))
            self.__hostname = url.split("://")[1]
            self.__mgmt_url = f"http://{self.__hostname}:8091"
            self.__username = username
            self.__password = password

    def create_collections(self, bucket: str, scope: str, names: List[str]) -> None:
        """
        A function that will create a specified set of collections in the specified scope
        which resides in the specified bucket

        :param bucket: The bucket name in which the scope resides
        :param scope: The scope in which to create the collections.  It will be created
                      if it doesn't already exist, unless it is the default scope
        :param names: The names of the collections to create
        """
        with self.__tracer.start_as_current_span("Create Scope", attributes={"cbl.scope.name": scope, "cbl.bucket.name": bucket}) as current_span:
            bucket_obj = _try_n_times(10, 1, False, self.__cluster.bucket, Bucket, bucket)
            c = bucket_obj.collections()
            try:
                if scope != "_default":
                    c.create_scope(scope)
            except ScopeAlreadyExistsException:
                pass

            for name in names:
                with self.__tracer.start_as_current_span("Create Collection", attributes={"cbl.scope.name": scope, "cbl.bucket.name": bucket, "cbl.collection.name": name}):
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
                        cbl_warning(f"{bucket}.{scope}.{name} appears to not be ready yet, waiting for 1 second...")
                        sleep(1.0)

                if not success:
                    raise CblTestError(f"Unable to properly create {bucket}.{scope}.{name} in Couchbase Server")


    def create_bucket(self, name: str):
        """
        Creates a bucket with a given name that Sync Gateway can use

        :param name: The name of the bucket to create
        """
        with self.__tracer.start_as_current_span("create_bucket", attributes={"cbl.bucket.name": name}):
            mgr = self.__cluster.buckets()
            settings = CreateBucketSettings(name=name, flush_enabled=True, ram_quota_mb=512)
            try:
                mgr.create_bucket(settings)
            except BucketAlreadyExistsException:
                pass

            # enableCrossClusterVersioning, this will no-op unless it is Server >= 7.6. This function needs to be retried
            def enable_cccv():
                r = requests.post(
                    f"{self.__mgmt_url}/pools/default/buckets/{name}",
                    {"enableCrossClusterVersioning": "true"},
                    auth=(self.__username, self.__password),
                )
                if r.status_code == 200:
                    return
                elif "Cross cluster versioning already enabled" in r.text:
                    return
                raise CblTestError(
                    f"Could not enable cross cluster versioning ({r.status_code}): {r.text}"
                    )

            _try_n_times(num_times=10, seconds_between=5, wait_before_first_try=False, func=enable_cccv, ret_type=None)  

    def drop_bucket(self, name: str):
        """
        Drops a bucket from the Couchbase cluster

        :param name: The name of the bucket to drop
        """
        with self.__tracer.start_as_current_span("drop_bucket", attributes={"cbl.bucket.name": name}):
            try:
                mgr = self.__cluster.buckets()
                mgr.drop_bucket(name)
            except BucketDoesNotExistException:
                pass

    def indexes_count(self, bucket: str) -> int:
        """
        Returns the number of indexes that are in the specified bucket

        :param bucket: The bucket to check for indexes
        """
        with self.__tracer.start_as_current_span("indexes_count", attributes={"cbl.bucket.name": bucket}):
            index_mgr = self.__cluster.query_indexes()
            indexes = list(index_mgr.get_all_indexes(bucket))
            return len(indexes)
    
    def run_query(self, query: str, bucket: str, scope: str = "_default", collection: str = "_default") -> List[Dict]:
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
        with self.__tracer.start_as_current_span("run_query", attributes={"cbl.query.name": actual_query}):
            query_obj = self.__cluster.query(actual_query)
            try:
                self.__cluster.query_indexes().create_primary_index(bucket, CreatePrimaryQueryIndexOptions(scope_name=scope, collection_name=collection))
            except QueryIndexAlreadyExistsException:
                pass

            return list(dict(result) for result in query_obj.execute())

    def start_xdcr(self, to_cbs, from_bucket: str, to_bucket: str):
        """
        Starts an XDCR replication from a bucket on the current cluster to a bucket on another cluster.

        :param to_cluster: The CouchbaseServer object to replicate to.
        :param from_bucket: The name of the bucket to replicate from.
        :param to_bucket: The name of the bucket to replicate to.
        """
        with self.__tracer.start_as_current_span(
            "start_xdcr",
            attributes={"cbl.from.bucket": from_bucket, "cbl.to.bucket": to_bucket},
        ):
            cluster_name = self.create_remote_cluster(to_cbs)
            r = requests.post(
                f"{self.__mgmt_url}/controller/createReplication",
                {
                    "name": cluster_name,
                    "toCluster": cluster_name,
                    "fromBucket": from_bucket,
                    "toBucket": to_bucket,
                    "replicationType": "continuous",
                    "mobile": "Active",
                },
                auth=(self.__username, self.__password),
            )
            if r.status_code == 200:
                return
            elif "already exists" in r.text:
                return
            raise CblTestError(f"Could not start XDCR: {r.text}")

    def create_remote_cluster(self, to_cbs: Self) -> str:
        with self.__tracer.start_as_current_span(
            "create_remote_cluster",
        ):
            cluster_name = to_cbs.__hostname
            auth = (self.__username, self.__password)
            url = f"{self.__mgmt_url}/pools/default/remoteClusters"

            # check if the remote cluster already exists
            r = requests.get(url, auth=auth)
            if r.status_code != 200:
                raise CblTestError(f"Could not get remote clusters via {url}: {r.text}")
            for cluster in r.json():
                if cluster_name in cluster["hostname"]:
                    return cluster_name
            r = requests.post(
                url,
                {
                    "hostname": to_cbs.__hostname,
                    "username": to_cbs.__username,
                    "password": to_cbs.__password,
                    "name": cluster_name,
                },
                auth=auth,
            )
            if r.status_code != 200:
                raise CblTestError(
                    f"Could not create remote cluster via {url}: {r.text}"
                )
            return cluster_name
