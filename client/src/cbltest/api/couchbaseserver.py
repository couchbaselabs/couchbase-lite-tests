from datetime import timedelta
from couchbase.cluster import Cluster
from couchbase.options import ClusterOptions
from couchbase.auth import PasswordAuthenticator
from couchbase.management.users import Role
from couchbase.management.buckets import CreateBucketSettings
from couchbase.exceptions import BucketAlreadyExistsException

class CouchbaseServer:
    """
    A class that interacts with a Couchbase Server cluster
    """
    def __init__(self, url: str, username: str, password: str):
        auth = PasswordAuthenticator(username, password)
        opts = ClusterOptions(auth)
        self.__cluster = Cluster(url, opts)
        self.__cluster.wait_until_ready(timedelta(seconds=10))

    def create_bucket(self, name: str):
        """
        Creates a bucket with a given name that Sync Gateway can use

        :param name: The name of the bucket to create
        """
        mgr = self.__cluster.buckets()
        user_mgr = self.__cluster.users()
        settings = CreateBucketSettings(name=name, flush_enabled=True, ram_quota_mb=512)
        try:
            mgr.create_bucket(settings)
            existing_user = user_mgr.get_user("admin").user
            roles = existing_user.roles
            roles.add(Role("bucket_full_access", name))
            roles.add(Role("bucket_admin", name))
            user_mgr.upsert_user(existing_user)
        except BucketAlreadyExistsException:
            pass

    def drop_bucket(self, name: str):
        """
        Drops a bucket from the Couchbase cluster

        :param name: The name of the bucket to drop
        """
        mgr = self.__cluster.buckets()
        mgr.drop_bucket(name)