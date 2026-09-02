"""
Models for the stats of Sync Gateway.

These are typed and keyed on the version to throw CblTestError if the version of Sync Gateway does not implement the stat.
"""

from typing import Any, Final, Self, cast

import packaging.version
from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, ValidationError, ValidationInfo, model_validator

from cbltest.api.error import CblTestError

# The oldest Sync Gateway the harness reads stats from. A stat this release already declared is
# a required field below, and a stat a later release added is an OptionalStat.
_MINIMUM_SYNC_GATEWAY_VERSION: Final = packaging.version.parse("3.2.0")


class _VersionedModel(BaseModel):
    """A model that remembers the Sync Gateway version whose payload it read."""

    # The version tells a stat the node is too old to have from one it renamed or dropped.
    _sgw_version: str | None = PrivateAttr(default=None)

    @model_validator(mode="after")
    def _record_sgw_version(self, info: ValidationInfo) -> Self:
        self._sgw_version = (info.context or {}).get("sgw_version")
        return self


class OptionalSection[Section: _StatsModel]:
    """
    A per-database section that Sync Gateway sends only for a database that enables the feature
    it counts, so reading it raises rather than answering None.
    """

    def __init__(self, model: type[Section]) -> None:
        self._model = model
        self._name = "unnamed"

    def __set_name__(self, owner: type, name: str) -> None:
        self._name = name

    def __get__(self, instance: Any, owner: type | None = None) -> Section:
        if instance is None:
            raise CblTestError(f"'{self._name}' is a section of a stats payload, not of a class")

        if self._name in instance._sections:
            return cast(Section, instance._sections[self._name])

        section = (instance.__pydantic_extra__ or {}).get(self._name)
        if section is None:
            raise CblTestError(f"Sync Gateway sent no '{self._name}' stats for the database '{instance._db_name}'")

        try:
            stats = self._model.model_validate(section, context={"sgw_version": instance._sgw_version})
        except ValidationError as exc:
            raise CblTestError(f"Sync Gateway sent an unexpected '{self._name}' section: {exc}") from exc

        instance._sections[self._name] = stats
        return stats


class OptionalStat:
    """
    A stat Sync Gateway does not always send: one that a later release added, or one that a
    section sends only when it has a value.  Reading one the payload lacks raises.
    """

    def __init__(self, added: str | None = None) -> None:
        if added is not None and packaging.version.parse(added) <= _MINIMUM_SYNC_GATEWAY_VERSION:
            raise CblTestError(
                f"Sync Gateway {added} is not later than {_MINIMUM_SYNC_GATEWAY_VERSION}, so every node the harness "
                "reads stats from sends this stat: declare it as a required field"
            )

        self._added = added
        self._name = "unnamed"

    def __set_name__(self, owner: type, name: str) -> None:
        self._name = name

    def __get__(self, instance: Any, owner: type | None = None) -> int:
        if instance is None:
            raise CblTestError(f"'{self._name}' is a stat of a stats payload, not of a class")

        stats = instance.__pydantic_extra__ or {}
        if self._name not in stats:
            raise CblTestError(f"This Sync Gateway sent no '{self._name}' stat: {self._reason(instance._sgw_version)}")

        # Extras skip pydantic's coercion, so the value is whatever the payload held.
        value = stats[self._name]
        if not isinstance(value, int):
            raise CblTestError(f"Sync Gateway sent the '{self._name}' stat as {type(value).__name__}, not an integer")

        return value

    def _reason(self, sgw_version: str | None) -> str:
        """Says why the stat is missing, naming the node's version when it reports one."""
        if self._added is None:
            return "Sync Gateway sends it only when it has a value for it"

        if sgw_version is None:
            return f"Sync Gateway {self._added} added it, and this node did not report its version"

        # A dev build reports major.minor only, so a stat that a patch release added can read as
        # absent for age on a node that in fact carries it.
        if packaging.version.parse(sgw_version) >= packaging.version.parse(self._added):
            return (
                f"Sync Gateway {self._added} added it and this node reports {sgw_version}, "
                "so the stat was renamed or removed"
            )

        return f"Sync Gateway {self._added} added it and this node reports {sgw_version}, so it is too old to send it"


class _StatsModel(_VersionedModel):
    """
    Base of the stats sections.  Extra keys are kept, so an ``OptionalStat`` can read a stat
    that the fields below do not declare.
    """

    model_config = ConfigDict(extra="allow", ignored_types=(OptionalStat,))


class ResourceUtilization(_StatsModel):
    """
    The ``resource_utilization`` section of the ``global`` stats in ``GET /_expvar``.
    """

    # The total number of bytes received (since node start-up) on the network interface to which the Sync Gateway
    # api.admin_interface is bound.
    admin_net_bytes_recv: int
    # The total number of bytes sent (since node start-up) on the network interface to which the Sync Gateway
    # api.admin_interface is bound.
    admin_net_bytes_sent: int
    # The total number of errors logged.
    error_count: int
    go_memstats_heapalloc: int
    go_memstats_heapidle: int
    go_memstats_heapinuse: int
    go_memstats_heapreleased: int
    go_memstats_pausetotalns: int
    go_memstats_stackinuse: int
    go_memstats_stacksys: int
    go_memstats_sys: int
    # Peak number of go routines since process start.
    goroutines_high_watermark: int
    # The total number of goroutines.
    num_goroutines: int
    # The CPU's utilization as percentage value.  The CPU usage calculation is performed based on user and system CPU
    # time, but it doesn't include components such as iowait.
    process_cpu_percent_utilization: float
    # The node CPU usage calculation based values from /proc of user + system since the last time this function was
    # called.
    node_cpu_percent_utilization: float
    # The number of background kv/query operations.
    idle_kv_ops: int
    idle_query_ops = OptionalStat("3.2.2")
    # The memory utilization (Resident Set Size) for the process, in bytes.
    process_memory_resident: int
    # The total number of bytes received (since node start-up) on the network interface to which the Sync Gateway
    # api.public_interface is bound.
    pub_net_bytes_recv: int
    # The total number of bytes sent (since node start-up) on the network interface to which Sync Gateway
    # api.public_interface is bound.
    pub_net_bytes_sent: int
    # The total memory available on the system in bytes.
    system_memory_total: int
    # The total number of warnings logged.
    warn_count: int
    # The total number of assertion failures logged. This is a good indicator of a bug and should be reported.
    assertion_fail_count = OptionalStat("3.2.4")
    # The total uptime.
    uptime: int


class ConfigStat(_StatsModel):
    """
    The ``config`` section of the ``global`` stats in ``GET /_expvar``.
    """

    # The number of times the bucket specified in a database config doesn't match the bucket it's found in.
    database_config_bucket_mismatches: int
    # The number of times the config was rolled back to an invalid state (conflicting collections)
    database_config_rollback_collection_collisions: int
    # The number of times a non-xattr config or registry document was loaded in xattr mode
    xattr_format_mismatches = OptionalStat("3.2.4")


class AuditStat(_StatsModel):
    """
    The ``audit`` section of the ``global`` stats in ``GET /_expvar``.
    """

    # The number of times an audit event was created/emitted/logged.
    num_audits_logged = OptionalStat("3.2.1")
    # The number of times an audit event was filtered by username.
    num_audits_filtered_by_user = OptionalStat("3.2.1")
    # The number of times an audit event was filtered by role.
    num_audits_filtered_by_role = OptionalStat("3.2.1")


class CacheStats(_StatsModel):
    """
    The ``cache`` section of one database's stats in ``GET /_expvar``.
    """

    # The total number of skipped sequences that were not found after 60 minutes and were abandoned.
    abandoned_seqs: int
    # The total number of active revisions in the channel cache.
    chan_cache_active_revs: int
    # The total number of transient bypass channel caches created to serve requests when the channel cache was at
    # capacity.
    chan_cache_bypass_count: int
    # The total number of channel caches added.  The metric doesn't decrease when a channel is removed. That is, it is
    # similar to chan_cache_num_channels but doesn't track removals.
    chan_cache_channels_added: int
    # The total number of channel cache channels evicted due to inactivity.
    chan_cache_channels_evicted_inactive: int
    # The total number of active channel cache channels evicted, based on 'not recently used' criteria.
    chan_cache_channels_evicted_nru: int
    # The total number of entries currently held across all channels' late-arriving-sequence queues (lateLogs).
    num_entries_in_late_feed = OptionalStat("4.1.0")
    # The total number of times a continuous _changes feed was forced to roll back to its low sequence because its
    # lastSequence was pruned from a channel's lateLogs (length/age cap firing on a lagging feed).
    late_feed_forced_rollbacks = OptionalStat("4.1.0")
    # The total number of channel cache compaction runs.
    chan_cache_compact_count: int
    # The total amount of time taken by channel cache compaction across all compaction runs.
    chan_cache_compact_time: int
    # The total number of channel cache requests fully served by the cache.
    chan_cache_hits: int
    # The total size of the largest channel cache.
    chan_cache_max_entries: int
    # The total number of channel cache requests not fully served by the cache.
    chan_cache_misses: int
    # The total number of channels being cached.
    chan_cache_num_channels: int
    # The total number of channel cache pending queries.
    chan_cache_pending_queries: int
    # The total number of removal revisions in the channel cache.
    chan_cache_removal_revs: int
    # The total number of tombstone revisions in the channel cache.
    chan_cache_tombstone_revs: int
    # The highest sequence number cached.  There may be skipped sequences lower than high_seq_cached.
    high_seq_cached: int
    # The highest contiguous sequence number that has been cached.
    high_seq_stable: int
    non_mobile_ignored_count: int
    # The total number of ambiguous IsSGWrite checks on the caching DCP feed that required a KV body fetch to resolve.
    issgwrite_kv_fetch_count = OptionalStat("4.1.0")
    # The total number of active channels.
    num_active_channels: int
    # The total number of skipped sequences. This is a cumulative value.
    num_skipped_seqs: int
    # The total number of pending sequences. These are out-of-sequence entries waiting to be cached.
    pending_seq_len: int
    # Total number of items in the rev cache
    revision_cache_num_items = OptionalStat("3.2.1")
    # The total number of revision cache bypass operations performed.
    rev_cache_bypass: int
    # The total number of revision cache hits.
    rev_cache_hits: int
    # The total number of revision cache misses.
    rev_cache_misses: int
    # Total memory used by the rev cache
    revision_cache_total_memory = OptionalStat("3.2.1")
    # Deprecated: DeprecatedSkippedSeqLen UNUSED
    skipped_seq_len: int
    # Deprecated: DeprecatedSkippedSeqCap UNUSED
    skipped_seq_cap: int
    # The number of nodes in skipped sequence skiplist data structure
    skipped_sequence_skip_list_nodes = OptionalStat("3.3.0")
    # The number of sequences currently in the skipped sequence slice
    current_skipped_seq_count: int
    # The total view_queries.
    view_queries: int


class CBLReplicationPullStats(_StatsModel):
    """
    The ``cbl_replication_pull`` section of one database's stats in ``GET /_expvar``.
    """

    # The total size of attachments pulled. This is the pre-compressed size.
    attachment_pull_bytes: int
    # The total number of attachments pulled.
    attachment_pull_count: int
    # The high watermark for the number of documents buffered during feed processing, waiting on a missing earlier
    # sequence.
    max_pending: int
    # The total number of active replications. This metric only counts continuous pull replications.
    num_replications_active: int
    # The total number of continuous pull replications in the active state.
    num_pull_repl_active_continuous: int
    # The total number of one-shot pull replications in the active state.
    num_pull_repl_active_one_shot: int
    # The total number of replications which have caught up to the latest changes.
    num_pull_repl_caught_up: int
    num_pull_repl_total_caught_up: int
    # The total number of new replications started (/_changes?since=0).
    num_pull_repl_since_zero: int
    # The total number of continuous pull replications.
    num_pull_repl_total_continuous: int
    # The total number of one-shot pull replications.
    num_pull_repl_total_one_shot: int
    # The total number of changes requested.
    request_changes_count: int
    request_changes_time: int
    # The total amount of time processing rev messages (revisions) during pull revision.
    rev_processing_time: int
    # The total number of rev messages processed during replication.
    rev_send_count: int
    # The total number of norev messages sent during replication.
    norev_send_count: int
    # The total number of replacement revs sent during replication.
    replacement_rev_send_count: int
    # The total number of errors in response to sending a rev message.
    rev_error_count: int
    # The total amount of time between Sync Gateway receiving a request for a revision and that revision being sent.
    rev_send_latency: int


class CBLReplicationPushStats(_StatsModel):
    """
    The ``cbl_replication_push`` section of one database's stats in ``GET /_expvar``.
    """

    # The total number of attachment bytes pushed.
    attachment_push_bytes: int
    # The total number of attachments pushed.
    attachment_push_count: int
    # The total number of documents pushed.
    doc_push_count: int
    # The total number of documents that failed to push.
    doc_push_error_count: int
    # The total number of changes and-or proposeChanges messages processed since node start-up.
    propose_change_count: int
    # The total time spent processing changes and/or proposeChanges messages.  The propose_change_time is not included
    # in the write_processing_time.
    propose_change_time: int
    # Total time spent processing writes. Measures complete request-to-response time for a write.
    write_processing_time: int
    # Cumulative number of writes that were throttled.
    write_throttled_count: int
    # Cumulative time spent throttling writes.
    write_throttled_time: int


class DatabaseStats(_StatsModel):
    """
    The ``database`` section of one database's stats in ``GET /_expvar``.
    """

    replication_bytes_received: int
    replication_bytes_sent: int
    # The compaction_attachment_start_time.
    compaction_attachment_start_time: int
    # The compaction_tombstone_start_time.
    compaction_tombstone_start_time: int
    # The total number of writes that left the document in a conflicted state. Includes new conflicts, and mutations
    # that don't resolve existing conflicts.
    conflict_write_count: int
    # The total number of instances during import when the document cas had changed, but the document was not imported
    # because the document body had not changed.
    crc32c_match_count: int
    # The total number of DCP mutations added to Sync Gateway's channel cache.
    dcp_caching_count: int
    # The total time between a DCP mutation arriving at Sync Gateway and being added to channel cache.
    dcp_caching_time: int
    # The total number of document mutations received by Sync Gateway over DCP.
    dcp_received_count: int
    # The time between a document write and that document being received by Sync Gateway over DCP. If the document was
    # written prior to Sync Gateway starting the feed, it is recorded as the time since the feed was started.
    dcp_received_time: int
    # The total number of bytes read via Couchbase Lite 2.x replication since Sync Gateway node startup.
    doc_reads_bytes_blip: int
    # The total number of bytes written as part of document writes since Sync Gateway node startup.
    doc_writes_bytes: int
    # The total number of bytes written as part of Couchbase Lite document writes since Sync Gateway node startup.
    doc_writes_bytes_blip: int
    # The total size of xattrs written (in bytes).
    doc_writes_xattr_bytes: int
    # Highest sequence number seen on the caching DCP feed.
    high_seq_feed: int
    # The total number of document writes where the Sync Gateway-generated HLV version exceeded the document CAS and
    # required a corrective re-stamp. A non-zero value indicates clock skew between Sync Gateway and Couchbase Server.
    hlv_version_cas_retry_count = OptionalStat("4.1.0")
    # The number of attachments compacted
    num_attachments_compacted: int
    # The total number of documents read via Couchbase Lite 2.x replication since Sync Gateway node startup.
    num_doc_reads_blip: int
    # The total number of documents read via the REST API since Sync Gateway node startup. Includes Couchbase Lite 1.x
    # replication.
    num_doc_reads_rest: int
    # The total number of documents written by any means (replication, rest API interaction or imports) since Sync
    # Gateway node startup.
    num_doc_writes: int
    # Total number of document writes that were rejected by Sync Gateway.
    num_doc_writes_rejected = OptionalStat("3.3.0")
    # The total number of requests sent over the public REST api
    num_public_rest_requests: int
    # The total number of active replications.
    num_replications_active: int
    # The total number of replications created since Sync Gateway node startup.
    num_replications_total: int
    num_tombstones_compacted: int
    # Number of bytes written over public interface for REST api
    public_rest_bytes_written: int
    # The total amount of bytes read over the public REST api
    public_rest_bytes_read: int
    # The value of the last sequence number assigned. Callers using Set should be holding a mutex or ensure concurrent
    # updates to this value are otherwise safe.
    last_sequence_assigned_value = OptionalStat("3.2.4")
    # The total number of sequence numbers assigned.
    sequence_assigned_count: int
    # The total number of high sequence lookups.
    sequence_get_count: int
    # The total number of times the sequence counter document has been incremented.
    sequence_incr_count: int
    # The total number of unused, reserved sequences released by Sync Gateway.
    sequence_released_count: int
    # The value of the last sequence number reserved (which may not yet be assigned). Callers using Set should be
    # holding a mutex or ensure concurrent updates to this value are otherwise safe.
    last_sequence_reserved_value = OptionalStat("3.2.4")
    # The total number of sequences reserved by Sync Gateway.
    sequence_reserved_count: int
    # The total number of corrupt sequences above the MaxSequencesToRelease threshold seen at the sequence allocator
    corrupt_sequence_count = OptionalStat("3.2.4")
    # The total number of warnings relating to the channel name size.
    warn_channel_name_size_count: int
    # The total number of warnings relating to the channel count exceeding the channel count threshold.
    warn_channels_per_doc_count: int
    # The total number of warnings relating to the grant count exceeding the grant count threshold.
    warn_grants_per_doc_count: int
    # The total number of warnings relating to the xattr sync data being larger than a configured threshold.
    warn_xattr_size_count: int
    # The total number of times that a sync function was evaluated for the database (across all collections).
    sync_function_count: int
    # The total time spent evaluating a sync function (across all collections).
    sync_function_time: int
    # The total sync time is a proxy for websocket connections. Tracking long lived and potentially idle connections.
    # This stat represents the continually growing number of connections per sec.
    total_sync_time: int
    # The total number of times that a sync function encountered an exception (across all collections).
    sync_function_exception_count: int
    # The total number of times a replication connection is rejected due ot it being over the threshold
    num_replications_rejected_limit: int
    # The total number of processed documents for resync on this database.
    resync_num_processed = OptionalStat("3.3.0")
    # The total number of changed documents for resync on this database.
    resync_num_changed = OptionalStat("3.3.0")
    # The number of documents targeted for resync for the current or most recent resync run on this database.
    resync_docs_targeted = OptionalStat("4.1.0")
    # The total number of documents that failed during resync on this database.
    resync_errors_total = OptionalStat("4.1.0")
    # The caching DCP feed's expvar map, which predates the Prometheus stats and is expvar only.
    cache_feed: dict[str, Any]
    # The import DCP feed's expvar map, which predates the Prometheus stats and is expvar only.
    import_feed: dict[str, Any]
    # The total number of errors that occurred that prevented the database from being initialized.
    total_init_fatal_errors = OptionalStat("3.2.3")
    # The total number of errors that occurred that prevented the database from being brought online.
    total_online_fatal_errors = OptionalStat("3.2.3")
    # Total number of requests to /_all_docs on the public interface.
    num_public_all_docs_requests = OptionalStat("3.3.0")
    # Total number of documents returned after filtering for /_all_docs on the public interface.
    num_docs_post_filter_public_all_docs = OptionalStat("3.3.0")
    # Total number of documents returned before filtering for /_all_docs on the public interface.
    num_docs_pre_filter_public_all_docs = OptionalStat("3.3.0")
    # Total number of tombstones received by Sync Gateway
    tombstone_count = OptionalStat("4.0.0")


class DeltaSyncStats(_StatsModel):
    """
    The ``delta_sync`` section of one database's stats in ``GET /_expvar``.

    ``deltas_requested`` counts the revisions a client asked for as a delta and ``deltas_sent``
    counts the ones Sync Gateway sent that way, so a gap between them is a fall back to a full body.
    """

    # The total number of requested deltas that were available in the revision cache.
    delta_cache_hit: int
    # The total number of requested deltas that were not available in the revision cache.
    delta_cache_miss: int
    # Number of items in delta cache
    delta_cache_num_items = OptionalStat("4.1.0")
    # The number of delta replications that have been run.
    delta_pull_replication_count: int
    # The total number of documents pushed as a delta from a previous revision.
    delta_push_doc_count: int
    # The total number of times a revision is sent as delta from a previous revision.
    deltas_requested: int
    # The total number of revisions sent to clients as deltas.
    deltas_sent: int


class SecurityStats(_StatsModel):
    """
    The ``security`` section of one database's stats in ``GET /_expvar``.
    """

    # The total number of unsuccessful authentications.
    auth_failed_count: int
    # The total number of successful authentications.
    auth_success_count: int
    # The total number of documents rejected by write access functions (requireAccess, requireRole, requireUser).
    num_access_errors: int
    # The total number of documents rejected by the sync_function.
    num_docs_rejected: int
    # The total time spent in authenticating all requests.
    total_auth_time: int


class SharedBucketImportStats(_StatsModel):
    """
    The ``shared_bucket_import`` section of one database's stats in ``GET /_expvar``.
    """

    # The total number of docs imported.
    import_count: int
    # The total number of imports cancelled due to cas failure.
    import_cancel_cas: int
    # The total number of errors arising as a result of a document import.
    import_error_count: int
    # The total time taken to process a document import.
    import_processing_time: int
    # The highest sequence number value imported.
    import_high_seq: int
    # The total number of import partitions.
    import_partitions: int
    # The total number of documents processed by the import feed.
    import_feed_processed_count = OptionalStat("3.3.0")


class CollectionStats(_StatsModel):
    """
    One entry of the ``per_collection`` map of a database's stats, keyed by 'scope.collection'.
    """

    # The total number of times that the sync_function is evaluated for this collection.
    sync_function_count: int
    # The total time spent evaluating the sync_function for this keyspace.
    sync_function_time: int
    # The total number of documents rejected by the sync_function for this collection.
    sync_function_reject_count: int
    # The total number of documents rejected by write access functions (requireAccess, requireRole, requireUser) for
    # this collection.
    sync_function_reject_access_count: int
    # The total number of times the sync function encountered an exception for this collection.
    sync_function_exception_count: int
    # The total number of documents imported to this collection since Sync Gateway node startup.
    import_count: int
    # The total number of documents read from this collection since Sync Gateway node startup (i.e. sending to a client)
    num_doc_reads: int
    # The total number of bytes read from this collection as part of document writes since Sync Gateway node startup.
    doc_reads_bytes: int
    # The total number of documents written to this collection since Sync Gateway node startup (i.e. receiving from a
    # client)
    num_doc_writes: int
    # The total number of bytes written to this collection as part of document writes since Sync Gateway node startup.
    doc_writes_bytes: int
    # The total number of processed documents for resync on this collection.
    resync_num_processed = OptionalStat("3.3.0")
    # The total number of changed documents for resync on this collection.
    resync_num_changed = OptionalStat("3.3.0")


class MigrationStats(_StatsModel):
    """
    The ``metadata_migration`` section of one database's stats in ``GET /_expvar``.
    """

    # Cumulative count of fallback keys observed by range scans across all passes.
    docs_scanned_total = OptionalStat("4.1.0")
    # Cumulative count of fallback docs successfully moved to primary (or deleted, for transient docs).
    docs_migrated = OptionalStat("4.1.0")
    # Number of out-of-scope keys observed on the most recent pass (sibling-DB or bucket-level docs).
    docs_out_of_scope = OptionalStat("4.1.0")
    # Number of unknown-prefix keys observed on the most recent pass.
    docs_unknown_prefix = OptionalStat("4.1.0")
    # Cumulative per-doc error count.
    errors = OptionalStat("4.1.0")
    # Cumulative count of seq-counter poison-pill applications. Typically 0 or 1 per migration run.
    seq_poison_pill_applied = OptionalStat("4.1.0")
    # Cumulative count of MigrateMetadata pass invocations.
    passes = OptionalStat("4.1.0")
    # Metadata migration runs that the orchestrator gave up on after the bounded pass loop exhausted itself without a
    # clean pass (zero unknown-prefix remaining AND zero per-doc errors on the same pass).
    abandoned_runs = OptionalStat("4.1.0")


class DbReplicatorStats(_StatsModel):
    """
    One entry of the ``replications`` map of a database's stats, keyed by replication ID.
    """

    # The total number of bytes in all the attachments that were pushed since replication started.
    sgr_num_attachment_bytes_pushed: int
    # The total number of attachments that were pushed since replication started.
    sgr_num_attachments_pushed: int
    # The total number of documents that were pushed since replication started.  Used by Inter-Sync Gateway and SG
    # Replicate.
    sgr_num_docs_pushed: int
    # The total number of documents that failed to be pushed since replication started.  Used by Inter-Sync Gateway and
    # SG Replicate
    sgr_num_docs_failed_to_push: int
    # The total number of pushed documents that conflicted since replication started.
    sgr_push_conflict_count: int
    # The total number of pushed documents that were rejected since replication started.
    sgr_push_rejected_count: int
    # The total number of deltas sent
    sgr_deltas_sent: int
    sgr_num_connect_attempts_pull: int
    sgr_num_reconnects_aborted_pull: int
    # The total number of bytes in all the attachments that were pulled since replication started.
    sgr_num_attachment_bytes_pulled: int
    # The total number of attachments that were pulled since replication started.
    sgr_num_attachments_pulled: int
    # The total number of documents that were pulled since replication started.
    sgr_num_docs_pulled: int
    # The total number of documents that were purged since replication started.
    sgr_num_docs_purged: int
    # The total number of document pulls that failed since replication started.
    sgr_num_docs_failed_to_pull: int
    # The total number of documents that were purged since replication started.
    sgr_deltas_recv: int
    # The total number of deltas requested
    sgr_deltas_requested: int
    # The total number of documents that were purged since replication started.
    sgr_docs_checked_recv: int
    sgr_num_connect_attempts_push: int
    sgr_num_reconnects_aborted_push: int
    # The total number of conflicting documents that were resolved successfully locally (by the active replicator).
    sgr_conflict_resolved_local_count: int
    # The total number of conflicting documents that were resolved successfully remotely (by the active replicator).
    sgr_conflict_resolved_remote_count: int
    # The total number of conflicting documents that were resolved successfully by a merge action (by the active
    # replicator)
    sgr_conflict_resolved_merge_count: int
    # Internal stats for the lengths of expectedSeqs/processedSeqs lists in the ISGR checkpointer.
    expected_seq_len = OptionalStat()
    expected_seq_len_post_cleanup = OptionalStat()
    processed_seq_len = OptionalStat()
    processed_seq_len_post_cleanup = OptionalStat()


class GlobalStat(BaseModel):
    """
    The ``syncgateway.global`` section of ``GET /_expvar``, which Sync Gateway initializes for
    the node itself rather than for a database.
    """

    resource_utilization: ResourceUtilization
    config: ConfigStat
    audit: AuditStat


class PerDatabaseStats(_VersionedModel):
    """
    One entry of the ``syncgateway.per_db`` map of ``GET /_expvar``, keyed by database name.

    Sync Gateway initializes the cache, replication, database, security and query sections for
    every database, and the rest only for a database that enables the feature they count, so
    those are ``OptionalSection`` and raise when the database does not.
    """

    model_config = ConfigDict(extra="allow", ignored_types=(OptionalSection,))

    cache: CacheStats
    cbl_replication_pull: CBLReplicationPullStats
    cbl_replication_push: CBLReplicationPushStats
    database: DatabaseStats
    security: SecurityStats
    # Every query contributes '<name>_query_count', '<name>_query_error_count' and '<name>_query_time'.
    gsi_views: dict[str, int]
    per_collection: dict[str, CollectionStats] = Field(default_factory=dict)
    replications: dict[str, DbReplicatorStats] = Field(default_factory=dict)
    _sections: dict[str, _StatsModel] = PrivateAttr(default_factory=dict)
    delta_sync = OptionalSection(DeltaSyncStats)
    shared_bucket_import = OptionalSection(SharedBucketImportStats)
    metadata_migration = OptionalSection(MigrationStats)
    _db_name: str = PrivateAttr(default="unknown")


class SyncGatewayExpvars(BaseModel):
    """
    The ``syncgateway`` section of ``GET /_expvar``.
    """

    global_stats: GlobalStat = Field(alias="global")
    per_db: dict[str, PerDatabaseStats]
    # The legacy sg-replicate counters, an expvar map keyed by replication, absent while no
    # replication has reported one.
    per_replication: dict[str, Any] = Field(default_factory=dict)

    def model_post_init(self, context: Any) -> None:
        # Only the map knows each database's name, which its sections name when they raise.
        for db_name, stats in self.per_db.items():
            stats._db_name = db_name


class Expvars(BaseModel):
    """
    The top level of ``GET /_expvar``.  Sync Gateway always sends the ``syncgateway`` section,
    so a payload without it fails validation.
    """

    syncgateway: SyncGatewayExpvars

    @classmethod
    def from_response(cls, resp: Any, sgw_version: str | None = None) -> "Expvars":
        """
        Reads a ``GET /_expvar`` response.

        :param resp: The parsed response body
        :param sgw_version: The version the node reports, which its stats name when one is absent
        """
        try:
            return cls.model_validate(resp, context={"sgw_version": sgw_version})
        except ValidationError as exc:
            raise CblTestError(f"GET /_expvar sent an unexpected payload: {exc}") from exc

    def database(self, db_name: str) -> PerDatabaseStats:
        """
        One database's stats, or raises when the node reports no database of that name.

        :param db_name: The name of the SGW database to inspect
        """
        per_db = self.syncgateway.per_db
        if db_name not in per_db:
            raise CblTestError(f"Sync Gateway reports no stats for a database named '{db_name}'")

        return per_db[db_name]
