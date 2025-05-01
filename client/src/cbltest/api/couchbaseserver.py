from datetime import timedelta
from time import sleep

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

            auth = PasswordAuthenticator(username, password)
            opts = ClusterOptions(auth)
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
