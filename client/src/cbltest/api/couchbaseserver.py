from datetime import timedelta
import time
from typing import Any, Callable, Dict, List, Optional, Type, TypeVar, Union, cast
from opentelemetry.trace import get_tracer

from couchbase.bucket import Bucket
from couchbase.cluster import Cluster
from couchbase.options import ClusterOptions
from couchbase.auth import PasswordAuthenticator
from couchbase.management.buckets import CreateBucketSettings, CreateBucketOptions
from couchbase.management.collections import CollectionSpec
from couchbase.exceptions import BucketAlreadyExistsException, BucketDoesNotExistException, ScopeAlreadyExistsException
from couchbase.exceptions import CollectionAlreadyExistsException

from cbltest.version import VERSION
from cbltest.api.error import CblTimeoutError

T = TypeVar("T")

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

    @staticmethod
    def _try_n_times(num_times: int,
                    seconds_between : Union[int, float],
                    func : Callable,
                    ret_type : Type[T],
                    *args : Any,
                    **kwargs : Dict[str, Any]
                    ) -> T:
        for _ in range(num_times):
            try:
                return cast(T, func(*args, **kwargs))
            except Exception:
                print(f'trying {func} failed, sleeping for {seconds_between} seconds...')
                time.sleep(seconds_between)

        raise CblTimeoutError(f"Failed to call {func} after {num_times} attempts!")

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
            bucket_obj = CouchbaseServer._try_n_times(10, 1, self.__cluster.bucket, Bucket, bucket)
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