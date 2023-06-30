from datetime import timedelta
from couchbase.cluster import Cluster
from couchbase.options import ClusterOptions
from couchbase.auth import PasswordAuthenticator
from couchbase.management.buckets import CreateBucketSettings
from couchbase.exceptions import BucketAlreadyExistsException

class CouchbaseServer:
    def __init__(self, url: str, username: str, password: str):
        auth = PasswordAuthenticator(username, password)
        opts = ClusterOptions(auth)
        self.__cluster = Cluster(url, opts)
        self.__cluster.wait_until_ready(timedelta(seconds=10))

    def create_bucket(self, name: str):
        mgr = self.__cluster.buckets()
        settings = CreateBucketSettings(name=name, flush_enabled=True, ram_quota_mb=512)
        try:
            mgr.create_bucket(settings)
        except BucketAlreadyExistsException:
            pass

    def drop_bucket(self, name: str):
        mgr = self.__cluster.buckets()
        mgr.drop_bucket(name)