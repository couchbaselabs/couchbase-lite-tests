from datetime import timedelta
from typing import List
from couchbase.cluster import Cluster
from couchbase.options import ClusterOptions
from couchbase.auth import PasswordAuthenticator
from couchbase.management.buckets import CreateBucketSettings
from couchbase.management.collections import CollectionSpec
from couchbase.exceptions import BucketAlreadyExistsException, BucketDoesNotExistException, ScopeAlreadyExistsException
from couchbase.exceptions import CollectionAlreadyExistsException

class CouchbaseServer:
    """
    A class that interacts with a Couchbase Server cluster
    """
    def __init__(self, url: str, username: str, password: str):
        if "://" not in url:
            url = f"couchbase://{url}"
            
        auth = PasswordAuthenticator(username, password)
        opts = ClusterOptions(auth)
        self.__cluster = Cluster(url, opts)
        self.__cluster.wait_until_ready(timedelta(seconds=10))

    def create_collections(self, bucket: str, scope: str, names: List[str]) -> None:
        bucket_obj = self.__cluster.bucket(bucket)
        c = bucket_obj.collections()
        try:
            if scope != "_default":
                c.create_scope(scope)
        except ScopeAlreadyExistsException:
            pass

        for name in names:
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
        try:
            mgr = self.__cluster.buckets()
            mgr.drop_bucket(name)
        except BucketDoesNotExistException:
            pass