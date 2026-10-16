"""
Models for the ``syncgateway`` section of Sync Gateway's ``GET /_expvar`` output.

The source of truth is ``base/stats.go`` in the sync_gateway repo, with descriptions from
``base/stats_descriptions.go``. A ``# new in X`` comment marks a stat that Sync Gateway X added.
A stat without one exists since 3.0.0.
An older Sync Gateway omits the stats it predates, and reading one raises StatNotPresentError.
Unknown keys from a newer Sync Gateway are kept as pydantic extras.
"""

from typing import TYPE_CHECKING, Any, Self

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, model_validator

from cbltest.api.error import CblTestError


class StatNotPresentError(CblTestError, AttributeError):
    """The Sync Gateway did not report the requested stat"""


def _stat(*, description: str | None = None, alias: str | None = None) -> Any:
    # default=None lets an older Sync Gateway omit the stat, and _StatGroup raises on access instead.
    # Field(default=None) would type the field as None, so return Any to keep it typed as int.
    return Field(default=None, description=description, alias=alias)


class _StatGroup(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True)

    # Where this group sits in the expvar output, e.g. syncgateway.per_db.travel.database
    _path: str = PrivateAttr(default="")

    def __getattribute__(self, name: str) -> Any:
        value = super().__getattribute__(name)
        if value is None and name in type(self).model_fields:
            # Python retries via __getattr__, so hasattr and getattr(..., default) see an AttributeError
            raise AttributeError(name)
        return value

    if not TYPE_CHECKING:
        # pydantic hides BaseModel.__getattr__ from type checkers the same way

        def __getattr__(self, name: str) -> Any:
            if name in type(self).model_fields:
                raise StatNotPresentError(f"Sync Gateway did not report {self._path or type(self).__qualname__}.{name}")
            return super().__getattr__(name)

    def _set_path(self, path: str) -> None:
        self._path = path
        for name, field in type(self).model_fields.items():
            value = self.__dict__[name]
            key = f"{path}.{field.alias or name}"
            if isinstance(value, _StatGroup):
                value._set_path(key)
            elif isinstance(value, dict):
                for child_key, child in value.items():
                    if isinstance(child, _StatGroup):
                        child._set_path(f"{key}.{child_key}")


class SyncGatewayStats(_StatGroup):
    """The ``syncgateway`` section of ``GET /_expvar``"""

    class Global(_StatGroup):
        """``syncgateway.global``"""

        class ResourceUtilization(_StatGroup):
            """``syncgateway.global.resource_utilization``"""

            admin_net_bytes_recv: int = _stat(
                description="The total number of bytes received (since node start-up) on the network interface to which the Sync Gateway api.admin_interface is bound. By default, that is the number of bytes received on 127.0.0.1:4985 since node start-up. Unit: bytes."
            )
            admin_net_bytes_sent: int = _stat(
                description="The total number of bytes sent (since node start-up) on the network interface to which the Sync Gateway api.admin_interface is bound. By default, that is the number of bytes sent on 127.0.0.1:4985 since node start-up. Unit: bytes."
            )
            assertion_fail_count: int = _stat(  # new in 3.2.4
                description="The total number of assertion failures logged. This is a good indicator of a bug and should be reported."
            )
            error_count: int = _stat(description="The total number of errors logged.")
            go_memstats_heapalloc: int = _stat(
                description='HeapAlloc is bytes of allocated heap objects. "Allocated" heap objects include all reachable objects, as well as unreachable objects that the garbage collector has not yet freed. Specifically, HeapAlloc increases as heap objects are allocated and decreases as the heap is swept and unreachable objects are freed. Sweeping occurs incrementally between GC cycles, so these two processes occur simultaneously, and as a result HeapAlloc tends to change smoothly (in contrast with the sawtooth that is typical of stop-the-world garbage collectors). Unit: bytes.'
            )
            go_memstats_heapidle: int = _stat(
                description="HeapIdle is bytes in idle (unused) spans. Idle spans have no objects in them. These spans could be (and may already have been) returned to the OS, or they can be reused for heap allocations, or they can be reused as stack memory. HeapIdle minus HeapReleased estimates the amount of memory that could be returned to the OS, but is being retained by the runtime so it can grow the heap without requesting more memory from the OS. If this difference is significantly larger than the heap size, it indicates there was a recent transient spike in live heap size. Unit: bytes."
            )
            go_memstats_heapinuse: int = _stat(
                description="HeapInuse is bytes in in-use spans. In-use spans have at least one object in them. These spans an only be used for other objects of roughly the same size. HeapInuse minus HeapAlloc estimates the amount of memory that has been dedicated to particular size classes, but is not currently being used. This is an upper bound on fragmentation, but in general this memory can be reused efficiently. Unit: bytes."
            )
            go_memstats_heapreleased: int = _stat(
                description="HeapReleased is bytes of physical memory returned to the OS. This counts heap memory from idle spans that was returned to the OS and has not yet been reacquired for the heap. Unit: bytes."
            )
            go_memstats_pausetotalns: int = _stat(
                description="PauseTotalNs is the cumulative nanoseconds in GC stop-the-world pauses since the program started. During a stop-the-world pause, all goroutines are paused and only the garbage collector can run. Unit: nanoseconds."
            )
            go_memstats_stackinuse: int = _stat(
                description="StackInuse is bytes in stack spans. In-use stack spans have at least one stack in them. These spans can only be used for other stacks of the same size. There is no StackIdle because unused stack spans are returned to the heap (and hence counted toward HeapIdle). Unit: bytes."
            )
            go_memstats_stacksys: int = _stat(
                description="StackSys is bytes of stack memory obtained from the OS. StackSys is StackInuse, plus any memory obtained directly from the OS for OS thread stacks (which should be minimal). Unit: bytes."
            )
            go_memstats_sys: int = _stat(
                description="Sys is the total bytes of memory obtained from the OS. Sys is the sum of the XSys fields below. Sys measures the virtual address space reserved by the Go runtime for the heap, stacks, and other internal data structures. It's likely that not all of the virtual address space is backed by physical memory at any given moment, though in general it all was at some point. Unit: bytes."
            )
            goroutines_high_watermark: int = _stat(description="Peak number of go routines since process start.")
            idle_kv_ops: int = _stat(description="The total number of idle kv operations.")  # new in 3.1.3.1
            idle_query_ops: int = _stat(description="The total number of idle query operations.")  # new in 3.2.2
            node_cpu_percent_utilization: float = _stat(  # new in 3.2.0
                description="The node CPU utilization as percentage value, since the last time this stat was called. The CPU usage calculation is performed based on user and system CPU time, but it does not include components such as iowait. Unit: percent."
            )
            num_goroutines: int = _stat(description="The total number of goroutines.")
            process_cpu_percent_utilization: float = _stat(  # deprecated in 3.2.0
                description="The CPU's utilization as percentage value * 10. The extra 10 multiplier is a mistake left for backwards compatibility. Please consider using node_cpu_percent_utilization. The CPU usage calculation is performed based on user and system CPU time, but it does not include components such as iowait. The derivation means that the values of process_cpu_percent_utilization and %Cpu, returned when running the top command, will differ Unit: percent."
            )
            process_memory_resident: int = _stat(
                description="The memory utilization (Resident Set Size) for the process, in bytes. Unit: bytes."
            )
            pub_net_bytes_recv: int = _stat(
                description="The total number of bytes received (since node start-up) on the network interface to which the Sync Gateway api.public_interface is bound. By default, that is the number of bytes received on 127.0.0.1:4984 since node start-up Unit: bytes."
            )
            pub_net_bytes_sent: int = _stat(
                description="The total number of bytes sent (since node start-up) on the network interface to which Sync Gateway api.public_interface is bound. By default, that is the number of bytes sent on 127.0.0.1:4984 since node start-up. Unit: bytes."
            )
            system_memory_total: int = _stat(
                description="The total memory available on the system in bytes. Unit: bytes."
            )
            uptime: int = _stat(description="The total uptime. Unit: nanoseconds.")
            warn_count: int = _stat(description="The total number of warnings logged.")

        class Config(_StatGroup):
            """``syncgateway.global.config``"""

            database_config_bucket_mismatches: int = _stat(  # new in 3.1.2
                description="The total number of times a database config is polled from a bucket that doesn't match the bucket specified in the database config."
            )
            database_config_rollback_collection_collisions: int = _stat(  # new in 3.1.4
                description="The total number of times a database config is rolled back to an invalid state (collection conflicts)."
            )
            xattr_format_mismatches: int = _stat(  # new in 3.2.4
                description="The total number of times a non-xattr config or registry document was loaded in xattr mode."
            )

        class Audit(_StatGroup):
            """``syncgateway.global.audit``, new in 3.2.1"""

            num_audits_filtered_by_role: int = _stat(description="The total number of audit events filtered by role.")
            num_audits_filtered_by_user: int = _stat(description="The total number of audit events filtered by user.")
            num_audits_logged: int = _stat(description="The total number of audit events logged.")

        resource_utilization: ResourceUtilization = _stat()
        config: Config = _stat()  # new in 3.1.2
        audit: Audit = _stat()  # new in 3.2.1

    class PerDatabase(_StatGroup):
        """``syncgateway.per_db.<db>``"""

        class Cache(_StatGroup):
            """``syncgateway.per_db.<db>.cache``"""

            abandoned_seqs: int = _stat(
                description="The total number of skipped sequences abandoned, based on cache.channel_cache.max_wait_skipped."
            )
            chan_cache_active_revs: int = _stat(
                description="The total number of active revisions in the channel cache."
            )
            chan_cache_bypass_count: int = _stat(
                description="The total number of transient bypass channel caches created to serve requests when the channel cache was at capacity."
            )
            chan_cache_channels_added: int = _stat(
                description="The total number of channel caches added. The metric doesn't decrease when a channel is removed. That is, it is similar to chan_cache_num_channels but doesn't track removals."
            )
            chan_cache_channels_evicted_inactive: int = _stat(
                description="The total number of channel cache channels evicted due to inactivity."
            )
            chan_cache_channels_evicted_nru: int = _stat(
                description="The total number of active channel cache channels evicted, based on 'not recently used' criteria."
            )
            chan_cache_compact_count: int = _stat(description="The total number of channel cache compaction runs.")
            chan_cache_compact_time: int = _stat(
                description="The total amount of time taken by channel cache compaction across all compaction runs. Unit: nanoseconds."
            )
            chan_cache_hits: int = _stat(
                description="The total number of channel cache requests fully served by the cache. This metric is useful in calculating the channel cache hit ratio: channel cache hit ratio = chan_cache_hits / (chan_cache_hits + chan_cache_misses)"
            )
            chan_cache_max_entries: int = _stat(
                description="The total size of the largest channel cache. This metric helps with channel cache tuning, and provides a hint on cache size variation (when compared to average cache size)."
            )
            chan_cache_misses: int = _stat(
                description="The total number of channel cache requests not fully served by the cache. This metric is useful when calculating the channel cache hit ratio: channel cache hit ratio = chan_cache_hits / (chan_cache_hits + chan_cache_misses)"
            )
            chan_cache_num_channels: int = _stat(
                description="The total number of channels being cached. The total number of channels being cached provides insight into potential max cache size requirements and also node usage (for example, chan_cache_num_channels * max_cache_size)."
            )
            chan_cache_pending_queries: int = _stat(description="The total number of channel cache pending queries.")
            chan_cache_removal_revs: int = _stat(
                description="The total number of removal revisions in the channel cache. This metric acts as a reminder that removals must be considered when tuning the channel cache size and also helps users understand whether they should be tuning tombstone retention policy (metadata purge interval) and running compact."
            )
            chan_cache_tombstone_revs: int = _stat(
                description="The total number of tombstone revisions in the channel cache. This metric acts as a reminder that tombstones and removals must be considered when tuning the channel cache size and also helps users understand whether they should be tuning tombstone retention policy (metadata purge interval), and running compact."
            )
            current_skipped_seq_count: int = _stat(  # new in 3.2.0
                description="The number of sequences currently in the skipped sequence slice."
            )
            high_seq_cached: int = _stat(
                description="The highest sequence number cached. Note: There may be skipped sequences lower than high_seq_cached."
            )
            high_seq_stable: int = _stat(description="The highest contiguous sequence number that has been cached.")
            issgwrite_kv_fetch_count: int = _stat(  # new in 4.1.0
                description="The total number of ambiguous IsSGWrite checks on the caching DCP feed that required a KV body fetch to resolve."
            )
            late_feed_forced_rollbacks: int = _stat(  # new in 4.1.0, internal
                description="The total number of times a continuous _changes feed was forced to roll back to its low sequence because its lastSequence had been pruned from a channel's lateLogs by the length or age cap."
            )
            non_mobile_ignored_count: int = _stat(
                description="Number of non mobile documents that were ignored off the cache feed."
            )
            num_active_channels: int = _stat(description="The total number of active channels.")
            num_entries_in_late_feed: int = _stat(  # new in 4.1.0, internal
                description="The total number of late-arriving-sequence entries currently held across all channels."
            )
            num_skipped_seqs: int = _stat(
                description="The total number of skipped sequences. This is a cumulative value"
            )
            pending_seq_len: int = _stat(
                description="The total number of pending sequences. These are out-of-sequence entries waiting to be cached."
            )
            rev_cache_bypass: int = _stat(description="The total number of revision cache bypass operations performed.")
            rev_cache_hits: int = _stat(
                description="The total number of revision cache hits. This metric can be used to calculate the ratio of revision cache hits: Rev Cache Hit Ratio = rev_cache_hits / (rev_cache_hits + rev_cache_misses)"
            )
            rev_cache_misses: int = _stat(
                description="The total number of revision cache misses. This metric can be used to calculate the ratio of revision cache misses: Rev Cache Miss Ratio = rev_cache_misses / (rev_cache_hits + rev_cache_misses)"
            )
            revision_cache_num_items: int = _stat(
                description="The total number of items in the revision cache."
            )  # new in 3.2.1
            revision_cache_total_memory: int = _stat(  # new in 3.2.1
                description="The approximation of total memory taken up by rev cache and delta cache for documents. This is measured by the raw document body, the channels allocated to a document and its revision history. Unit: bytes."
            )
            skipped_seq_cap: int = _stat(  # new in 3.2.0, deprecated in 3.2.2
                description="The current capacity of the skipped sequence slice."
            )
            skipped_seq_len: int = _stat(  # deprecated in 3.2.2
                description="The current length of the pending skipped sequence slice."
            )
            skipped_sequence_skip_list_nodes: int = _stat(  # new in 3.3.0, internal
                description="The total number of nodes in the skipped sequence skiplist."
            )
            view_queries: int = _stat(description="The total view_queries.")

        class CBLReplicationPull(_StatGroup):
            """``syncgateway.per_db.<db>.cbl_replication_pull``"""

            attachment_pull_bytes: int = _stat(
                description="The total size of attachments pulled. This is the pre-compressed size. Unit: bytes."
            )
            attachment_pull_count: int = _stat(description="The total number of attachments pulled.")
            max_pending: int = _stat(
                description="The high watermark for the number of documents buffered during feed processing, waiting on a missing earlier sequence."
            )
            norev_send_count: int = _stat(
                description="The total number of norev messages sent during replication."
            )  # new in 3.2.0
            num_pull_repl_active_continuous: int = _stat(
                description="The total number of continuous pull replications in the active state."
            )
            num_pull_repl_active_one_shot: int = _stat(
                description="The total number of one-shot pull replications in the active state."
            )
            num_pull_repl_caught_up: int = _stat(
                description="The total number of replications which have caught up to the latest changes."
            )
            num_pull_repl_since_zero: int = _stat(
                description="The total number of new replications started (/_changes?since=0)."
            )
            num_pull_repl_total_caught_up: int = _stat(
                description="The total number of pull replications which have caught up to the latest changes across all replications."
            )
            num_pull_repl_total_continuous: int = _stat(description="The total number of continuous pull replications.")
            num_pull_repl_total_one_shot: int = _stat(description="The total number of one-shot pull replications.")
            num_replications_active: int = _stat(description="The total number of active replications.")
            replacement_rev_send_count: int = _stat(  # new in 3.2.0
                description="The total number of replacement revisions sent instead of a norev during replication."
            )
            request_changes_count: int = _stat(
                description="The total number of changes requested. This metric can be used to calculate the latency of requested changes: changes request latency = request_changes_time / request_changes_count"
            )
            request_changes_time: int = _stat(
                description="Total time taken to handle changes request response. This metric can be used to calculate the latency of requested changes: changes request latency = request_changes_time / request_changes_count Unit: nanoseconds."
            )
            rev_error_count: int = _stat(  # new in 3.2.0
                description="The total number of rev messages that were failed to be processed during replication."
            )
            rev_processing_time: int = _stat(
                description="The total amount of time processing rev messages (revisions) during pull revision. This metric can be used with rev_send_count to calculate the average processing time per revision: average processing time per revision = rev_processing_time / rev_send_count Unit: nanoseconds."
            )
            rev_send_count: int = _stat(
                description="The total number of rev messages processed during replication. This metric can be used with rev_processing_time to calculate the average processing time per revision: average processing time per revision = rev_processing_time / rev_send_count"
            )
            rev_send_latency: int = _stat(
                description="The total amount of time between Sync Gateway receiving a request for a revision and that revision being sent. In a pull replication, Sync Gateway sends a /_changes request to the client and the client responds with the list of revisions it wants to receive. So, rev_send_latency measures the time between the client asking for those revisions and Sync Gateway sending them to the client. Note: Measuring time from the /_changes response means that this stat will vary significantly depending on the changes batch size A larger batch size will result in a spike of this stat, even if the processing time per revision is unchanged. A more useful stat might be the average processing time per revision: average processing time per revision = rev_processing_time] / rev_send_count Unit: nanoseconds."
            )

        class CBLReplicationPush(_StatGroup):
            """``syncgateway.per_db.<db>.cbl_replication_push``"""

            attachment_push_bytes: int = _stat(description="The total number of attachment bytes pushed. Unit: bytes.")
            attachment_push_count: int = _stat(description="The total number of attachments pushed.")
            doc_push_count: int = _stat(description="The total number of documents pushed.")
            doc_push_error_count: int = _stat(description="The total number of documents that failed to push.")
            propose_change_count: int = _stat(
                description="The total number of changes and-or proposeChanges messages processed since node start-up. The propose_change_count stat can be useful when: (a). Assessing the number of redundant requested changes being pushed by the client. Do this by comparing the propose_change_count value with the number of actual writes num_doc_writes, which could indicate that clients are pushing changes already known to Sync Gateway. (b). Identifying situations where push replications are unexpectedly being restarted from zero."
            )
            propose_change_time: int = _stat(
                description="The total time spent processing changes and/or proposeChanges messages. The propose_change_time stat can be useful in diagnosing push replication issues arising from potential bottlenecks changes and-or proposeChanges processing. Note: The propose_change_time is not included in the write_processing_time Unit: nanoseconds."
            )
            write_processing_time: int = _stat(
                description="Total time spent processing writes. Measures complete request-to-response time for a write. The write_processing_time stat can be useful when: (a). Determining the average time per write: average time per write = write_processing_time / num_doc_writes stat value (b). Assessing the benefit of adding additional Sync Gateway nodes, as it can point to Sync Gateway being a bottleneck (c). Troubleshooting slow push replication, in which case it ought to be considered in conjunction with sync_function_time Unit: nanoseconds."
            )
            write_throttled_count: int = _stat(  # new in 3.1.4
                description="The total number of times a revision was throttled during push replication from clients. The write_throttled_count stat can be useful to to determine an appropriate limit of concurrent revisions for each client. There's a direct tradeoff with memory and CPU usage for replicating clients and large amounts of concurrent revisions."
            )
            write_throttled_time: int = _stat(  # new in 3.1.4
                description="The total time (in nanoseconds) waiting for an available slot to handle a pushed revision after being throttled. The write_throttled_time stat can be useful to determine whether clients are waiting too long for an available slot to push a revision. There's a direct tradeoff with memory and CPU usage for replicating clients and large amounts of concurrent revisions. Unit: nanoseconds."
            )

        class Database(_StatGroup):
            """``syncgateway.per_db.<db>.database``"""

            # cache_feed and import_feed hold DCP feed counters with no fixed key set
            cache_feed: dict[str, Any] = _stat()
            compaction_attachment_start_time: int = _stat(
                description="The compaction_attachment_start_time Unit: unix timestamp."
            )
            compaction_tombstone_start_time: int = _stat(
                description="The compaction_tombstone_start_time. Unit: unix timestamp."
            )
            conflict_write_count: int = _stat(
                description="The total number of writes that left the document in a conflicted state. Includes new conflicts, and mutations that don't resolve existing conflicts."
            )
            corrupt_sequence_count: int = _stat(  # new in 3.2.4
                description="The total number of corrupt sequences detected at the sequence allocator. Documents that have a corrupt sequence that trigger release of sequences above the MaxSequenceToRelease threshold will have their update cancelled."
            )
            crc32c_match_count: int = _stat(
                description="The total number of instances during import when the document cas had changed, but the document was not imported because the document body had not changed."
            )
            dcp_caching_count: int = _stat(
                description="The total number of DCP mutations added to Sync Gateway's channel cache. Can be used with dcp_caching_time to monitor cache processing latency. That is, the time between seeing a change on the DCP feed and when it's available in the channel cache: DCP cache latency = dcp_caching_time / dcp_caching_count"
            )
            dcp_caching_time: int = _stat(
                description="The total time between a DCP mutation arriving at Sync Gateway and being added to channel cache. This metric can be used with dcp_caching_count to monitor cache processing latency. That is, the time between seeing a change on the DCP feed and when it's available in the channel cache: dcp_cache_latency = dcp_caching_time / dcp_caching_count Unit: nanoseconds."
            )
            dcp_received_count: int = _stat(
                description="The total number of document mutations received by Sync Gateway over DCP."
            )
            dcp_received_time: int = _stat(
                description="The time between a document write and that document being received by Sync Gateway over DCP. If the document was written prior to Sync Gateway starting the feed, it is recorded as the time since the feed was started. This metric can be used to monitor DCP feed processing latency Unit: nanoseconds."
            )
            doc_reads_bytes_blip: int = _stat(
                description="The total number of bytes read via Couchbase Lite 2.x replication since Sync Gateway node startup. Unit: bytes."
            )
            doc_writes_bytes: int = _stat(
                description="The total number of bytes written as part of document writes since Sync Gateway node startup. Unit: bytes."
            )
            doc_writes_bytes_blip: int = _stat(
                description="The total number of bytes written as part of Couchbase Lite document writes since Sync Gateway node startup. Unit: bytes."
            )
            doc_writes_xattr_bytes: int = _stat(description="The total size of xattrs written (in bytes). Unit: bytes.")
            high_seq_feed: int = _stat(description="Highest sequence number seen on the caching DCP feed.")
            hlv_version_cas_retry_count: int = _stat(  # new in 4.1.0, internal
                description="The total number of document writes where the Sync Gateway-generated HLV version exceeded the document CAS and required a corrective re-stamp. A non-zero value indicates clock skew between Sync Gateway and Couchbase Server."
            )
            import_feed: dict[str, Any] = _stat()
            invalid_rev_tree_count: int = _stat(  # new in 4.2.0, internal
                description="The total number of times a document's revision tree was found to be invalid at read or write time."
            )
            last_sequence_assigned_value: int = _stat(
                description="The value of the last sequence number assigned."
            )  # new in 3.2.4
            last_sequence_reserved_value: int = _stat(  # new in 3.2.4
                description="The value of the last sequence number reserved (which may not yet be assigned)"
            )
            num_attachments_compacted: int = _stat(description="The number of attachments compacted import_feed")
            num_doc_reads_blip: int = _stat(
                description="The total number of documents read via Couchbase Lite 2.x replication since Sync Gateway node startup."
            )
            num_doc_reads_rest: int = _stat(
                description="The total number of documents read via the REST API since Sync Gateway node startup. Includes Couchbase Lite 1.x replication."
            )
            num_doc_writes: int = _stat(
                description="The total number of documents written by any means (replication, rest API interaction or imports) since Sync Gateway node startup."
            )
            num_doc_writes_rejected: int = _stat(  # new in 3.3.0, internal
                description="NumDocWritesRejected is the total number of document writes that were rejected by Sync Gateway when the unsupported option RejectWritesWithSkippedSequences."
            )
            num_docs_post_filter_public_all_docs: int = _stat(  # new in 3.3.0, internal
                description="The total number of documents returned on all public /_all_docs requests after filtering"
            )
            num_docs_pre_filter_public_all_docs: int = _stat(  # new in 3.3.0, internal
                description="The total number of documents returned on all public /_all_docs requests before filtering"
            )
            num_public_all_docs_requests: int = _stat(  # new in 3.3.0, internal
                description="The total number of requests sent over the public REST api for /_all_docs."
            )
            num_public_rest_requests: int = _stat(  # new in 3.2.0
                description="The total number of requests sent over the public REST api."
            )
            num_replications_active: int = _stat(description="The total number of active replications.")
            num_replications_rejected_limit: int = _stat(  # new in 3.2.0
                description="The total number of times a replication connection is rejected due to it being over the threshold."
            )
            num_replications_total: int = _stat(
                description="The total number of replications created since Sync Gateway node startup."
            )
            num_tombstones_compacted: int = _stat(
                description="Number of tombstones compacted through tombstone compaction task on the database."
            )
            public_rest_bytes_read: int = _stat(  # new in 3.2.0
                description="The total amount of bytes read over the public REST api Unit: bytes."
            )
            public_rest_bytes_written: int = _stat(  # new in 3.2.0
                description="Number of bytes written over public interface for REST api Unit: bytes."
            )
            replication_bytes_received: int = _stat(  # new in 3.2.0
                description="Total bytes received over replications to the database. Unit: bytes."
            )
            replication_bytes_sent: int = _stat(  # new in 3.2.0
                description="Total bytes sent over replications from the database. Unit: bytes."
            )
            resync_docs_targeted: int = _stat(  # new in 4.1.0
                description="The number of documents targeted for resync for the current or most recent resync run on this database."
            )
            resync_errors_total: int = _stat(  # new in 4.1.0
                description="The total number of documents that failed during resync on this database."
            )
            resync_num_changed: int = _stat(  # new in 3.3.0
                description="The total number of changed documents for resync on this database."
            )
            resync_num_processed: int = _stat(  # new in 3.3.0
                description="The total number of processed documents for resync on this database."
            )
            sequence_assigned_count: int = _stat(description="The total number of sequence numbers assigned.")
            sequence_get_count: int = _stat(description="The total number of high sequence lookups.")
            sequence_incr_count: int = _stat(
                description="The total number of times the sequence counter document has been incremented."
            )
            sequence_released_count: int = _stat(description="The total number of unused, reserved sequences released.")
            sequence_reserved_count: int = _stat(description="The total number of sequences reserved.")
            sync_function_count: int = _stat(
                description="The total number of times that the sync_function is evaluated. The {sync_function_count_ stat is useful in assessing the usage of the sync_function, when used in conjunction with the sync_function_time."
            )
            sync_function_exception_count: int = _stat(
                description="The total number of times that a sync function encountered an exception (across all collections)."
            )
            sync_function_time: int = _stat(
                description="The total time spent evaluating the sync_function. The sync_function_time stat can be useful when: (a). Troubleshooting excessively long push times, where it can help identify potential sync_function bottlenecks (for example, those arising from complex, or inefficient, sync_function design. (b). Assessing the overall contribution of the sync_function processing to overall push replication write times. Unit: nanoseconds."
            )
            tombstone_count: int = _stat(
                description="The total number of tombstones processed by database"
            )  # new in 4.0.0
            total_init_fatal_errors: int = _stat(  # new in 3.2.3
                description="The total number of errors that occurred that prevented the database from being initialized."
            )
            total_online_fatal_errors: int = _stat(  # new in 3.2.3
                description="The total number of errors that occurred that prevented the database from being brought online."
            )
            total_sync_time: int = _stat(  # new in 3.2.0
                description="The total total sync time is a proxy for websocket connections. Tracking long lived and potentially idle connections. This stat represents the continually growing number of connections per sec. Unit: seconds."
            )
            warn_channel_name_size_count: int = _stat(
                description="The total number of warnings relating to the channel name size."
            )
            warn_channels_per_doc_count: int = _stat(
                description="The total number of warnings relating to the channel count exceeding the channel count threshold."
            )
            warn_grants_per_doc_count: int = _stat(
                description="The total number of warnings relating to the grant count exceeding the grant count threshold."
            )
            warn_xattr_size_count: int = _stat(
                description="The total number of warnings relating to the xattr sync data being larger than a configured threshold."
            )

        class DeltaSync(_StatGroup):
            """``syncgateway.per_db.<db>.delta_sync``, present only when delta sync is on"""

            delta_cache_hit: int = _stat(
                description="The total number of requested deltas that were available in the revision cache."
            )
            delta_cache_miss: int = _stat(
                description="The total number of requested deltas that were not available in the revision cache."
            )
            delta_cache_num_items: int = _stat(
                description="The total number of deltas stored in the delta cache."
            )  # new in 4.1.0
            delta_pull_replication_count: int = _stat(
                description="The number of delta replications that have been run."
            )
            delta_push_doc_count: int = _stat(
                description="The total number of documents pushed as a delta from a previous revision."
            )
            deltas_requested: int = _stat(
                description="The total number of times a client requested a revision as a delta from a previous revision."
            )
            deltas_sent: int = _stat(description="The total number of revisions sent to clients as deltas.")

        class Replication(_StatGroup):
            """``syncgateway.per_db.<db>.replications.<replication_id>`` (Inter-Sync Gateway Replication)"""

            expected_seq_len: int = _stat(
                description="The length of expectedSeqs list in the ISGR checkpointer."
            )  # new in 3.1.0
            expected_seq_len_post_cleanup: int = _stat(  # new in 3.1.0
                description="The length of expectedSeqs list in the ISGR checkpointer after the cleanup task has been run."
            )
            processed_seq_len: int = _stat(
                description="The length of processedSeqs list in the ISGR checkpointer."
            )  # new in 3.1.0
            processed_seq_len_post_cleanup: int = _stat(  # new in 3.1.0
                description="The length of processedSeqs list in the ISGR checkpointer after the cleanup task has been run."
            )
            sgr_conflict_resolved_local_count: int = _stat(
                description="The total number of conflicting documents that were resolved successfully locally (by the active replicator)"
            )
            sgr_conflict_resolved_merge_count: int = _stat(
                description="The total number of conflicting documents that were resolved successfully by a merge action (by the active replicator)"
            )
            sgr_conflict_resolved_remote_count: int = _stat(
                description="The total number of conflicting documents that were resolved successfully remotely (by the active replicator)"
            )
            sgr_deltas_recv: int = _stat(description="The total number of deltas received.")
            sgr_deltas_requested: int = _stat(description="The total number of deltas requested.")
            sgr_deltas_sent: int = _stat(description="The total number of deltas sent.")
            sgr_docs_checked_recv: int = _stat(
                description="The total number of document changes received over changes message."
            )
            sgr_docs_checked_sent: int = _stat(
                description="The total number of documents checked for changes since replication started. This represents the number of potential change notifications pushed by Sync Gateway. This is not necessarily the number of documents pushed, as a given target might already have the change and this is used by Inter-Sync Gateway and SG Replicate. This metric can be useful when analyzing replication history, and to filter by active replications."
            )
            sgr_num_attachment_bytes_pulled: int = _stat(
                description="The total number of bytes in all the attachments that were pulled since replication started. Unit: bytes."
            )
            sgr_num_attachment_bytes_pushed: int = _stat(
                description="The total number of bytes in all the attachments that were pushed since replication started. Unit: bytes."
            )
            sgr_num_attachments_pulled: int = _stat(
                description="The total number of attachments that were pulled since replication started."
            )
            sgr_num_attachments_pushed: int = _stat(
                description="The total number of attachments that were pushed since replication started."
            )
            sgr_num_connect_attempts_pull: int = _stat(
                description="Number of connection attempts made for pull replication connection."
            )
            sgr_num_connect_attempts_push: int = _stat(
                description="Number of connection attempts made for push replication connection."
            )
            sgr_num_docs_failed_to_pull: int = _stat(
                description="The total number of document pulls that failed since replication started."
            )
            sgr_num_docs_failed_to_push: int = _stat(
                description="The total number of documents that failed to be pushed since replication started. Used by Inter-Sync Gateway and SG Replicate."
            )
            sgr_num_docs_pulled: int = _stat(
                description="The total number of documents that were pulled since replication started."
            )
            sgr_num_docs_purged: int = _stat(
                description="The total number of documents that were purged since replication started."
            )
            sgr_num_docs_pushed: int = _stat(
                description="The total number of documents that were pushed since replication started. Used by Inter-Sync Gateway and SG Replicate."
            )
            sgr_num_reconnects_aborted_pull: int = _stat(
                description="Number of times pull replication connection reconnect loops have failed."
            )
            sgr_num_reconnects_aborted_push: int = _stat(
                description="Number of times push replication connection reconnect loops have failed."
            )
            sgr_push_conflict_count: int = _stat(
                description="The total number of pushed documents that conflicted since replication started."
            )
            sgr_push_rejected_count: int = _stat(
                description="The total number of pushed documents that were rejected since replication started."
            )

        class Security(_StatGroup):
            """``syncgateway.per_db.<db>.security``"""

            auth_failed_count: int = _stat(
                description="The total number of unsuccessful authentications. This metric is useful in monitoring the number of authentication errors."
            )
            auth_success_count: int = _stat(
                description="The total number of successful authentications. This metric is useful in monitoring the number of authenticated requests."
            )
            num_access_errors: int = _stat(
                description="The total number of documents rejected by write access functions (requireAccess, requireRole, requireUser)."
            )
            num_docs_rejected: int = _stat(description="The total number of documents rejected by the sync_function.")
            total_auth_time: int = _stat(
                description="The total time spent in authenticating all requests. This metric can be compared with auth_success_count and auth_failed_count to derive an average success and-or fail rate. Unit: nanoseconds."
            )

        class SharedBucketImport(_StatGroup):
            """``syncgateway.per_db.<db>.shared_bucket_import``, present only when import is on"""

            import_cancel_cas: int = _stat(description="The total number of imports cancelled due to cas failure.")
            import_count: int = _stat(
                description="The total number of docs imported across all collections in the bucket. For a per-collection breakdown see the collection-scoped import_count."
            )
            import_error_count: int = _stat(
                description="The total number of errors arising as a result of a document import."
            )
            import_feed_processed_count: int = _stat(
                description="The total number of documents processed by import feed."
            )  # new in 3.3.0
            import_high_seq: int = _stat(description="The highest sequence number value imported.")
            import_partitions: int = _stat(description="The total number of import partitions.")
            import_processing_time: int = _stat(
                description="The total time taken to process a document import. Unit: nanoseconds."
            )

        class MetadataMigration(_StatGroup):
            """
            ``syncgateway.per_db.<db>.metadata_migration``, new in 4.1.0.
            Present only when the database uses the system metadata collection.
            """

            abandoned_runs: int = _stat(
                description='The total number of metadata migration runs that the orchestrator gave up on after the bounded pass loop exhausted itself without a clean pass. Runs that exit early via a hard error from MigrateMetadata, or are stopped cooperatively via the terminator, are not counted here. This stat specifically captures the "hit the retry ceiling" failure mode, useful for distinguishing transient/abortive errors from buckets that need operator intervention.'
            )
            docs_migrated: int = _stat(
                description="The total number of metadata docs successfully moved from the fallback collection to the primary collection (or deleted, for transient docs)."
            )
            docs_out_of_scope: int = _stat(
                description="The number of fallback keys classified as out-of-scope on the most recent pass (sibling-DB or bucket-level docs not owned by this database)."
            )
            docs_scanned_total: int = _stat(
                description="The total number of fallback keys observed by metadata migration range scans across all passes."
            )
            docs_unknown_prefix: int = _stat(
                description="The number of fallback keys with an unrecognised prefix observed on the most recent pass — these are left in place on the source collection and do not block completion."
            )
            errors: int = _stat(
                description="The total number of per-doc errors observed during metadata migration moves or deletes across all passes."
            )
            passes: int = _stat(
                description="The total number of MigrateMetadata range-scan passes executed for this database."
            )
            seq_poison_pill_applied: int = _stat(
                description="The total number of times this node applied the seq-counter poison pill to initiate fallback→primary sequence handoff. Typically 0 or 1 per migration run."
            )

        class Collection(_StatGroup):
            """``syncgateway.per_db.<db>.per_collection.<scope>.<collection>``, new in 3.1.0"""

            doc_reads_bytes: int = _stat(
                description="The total number of bytes read from this collection as part of document reads since Sync Gateway node startup. Unit: bytes."
            )
            doc_writes_bytes: int = _stat(
                description="The total number of bytes written to this collection as part of document writes since Sync Gateway node startup. Unit: bytes."
            )
            import_count: int = _stat(
                description="The total number of documents imported to this collection since Sync Gateway node startup."
            )
            num_doc_reads: int = _stat(
                description="The total number of documents read from this collection since Sync Gateway node startup (i.e. sending to a client)"
            )
            num_doc_writes: int = _stat(
                description="The total number of documents written to this collection since Sync Gateway node startup (i.e. receiving from a client)"
            )
            resync_num_changed: int = _stat(  # new in 3.3.0
                description="The total number of changed documents for resync on this collection."
            )
            resync_num_processed: int = _stat(  # new in 3.3.0
                description="The total number of processed documents for resync on this collection."
            )
            sync_function_count: int = _stat(
                description="The total number of times that the sync_function is evaluated for this collection."
            )
            sync_function_exception_count: int = _stat(
                description="The total number of times the sync function encountered an exception for this collection."
            )
            sync_function_reject_access_count: int = _stat(
                description="The total number of documents rejected by write access functions (requireAccess, requireRole, requireUser) for this collection."
            )
            sync_function_reject_count: int = _stat(
                description="The total number of documents rejected by the sync_function for this collection."
            )
            sync_function_time: int = _stat(
                description="The total time spent evaluating the sync_function for this keyspace. Unit: nanoseconds."
            )

        cache: Cache = _stat()
        cbl_replication_pull: CBLReplicationPull = _stat()
        cbl_replication_push: CBLReplicationPush = _stat()
        database: Database = _stat()
        delta_sync: DeltaSync = _stat()
        # Keys are <query_name>_query_count, <query_name>_query_error_count and <query_name>_query_time
        gsi_views: dict[str, int] = Field(default_factory=dict)
        metadata_migration: MetadataMigration = _stat()  # new in 4.1.0
        per_collection: dict[str, Collection] = Field(default_factory=dict)  # new in 3.1.0
        replications: dict[str, Replication] = Field(default_factory=dict)
        security: Security = _stat()
        shared_bucket_import: SharedBucketImport = _stat()

        def collection(self, scope: str, collection: str) -> Collection:
            """
            Gets the stats for one collection of the database.

            :param scope: The scope that contains the collection
            :param collection: The name of the collection
            """
            key = f"{scope}.{collection}"
            if key not in self.per_collection:
                raise StatNotPresentError(
                    f"Sync Gateway reported no stats for collection {key!r} in {self._path}, "
                    f"it reports: {', '.join(self.per_collection) or 'none'}"
                )
            return self.per_collection[key]

    global_stats: Global = _stat(alias="global")
    per_db: dict[str, PerDatabase] = Field(default_factory=dict)
    # SG Replicate 1.x stats, keyed by replication ID. Recent versions leave this empty.
    per_replication: dict[str, dict[str, int]] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _name_groups(self) -> Self:
        self._set_path("syncgateway")
        return self

    @classmethod
    def from_expvar(cls, expvar: dict[str, Any]) -> Self:
        """
        Parses the full ``GET /_expvar`` response body.

        :param expvar: The JSON body of the response
        """
        return cls.model_validate(expvar["syncgateway"])

    def db(self, db_name: str) -> PerDatabase:
        """
        Gets the stats for one database.

        :param db_name: The name of the database
        """
        if db_name not in self.per_db:
            raise StatNotPresentError(
                f"Sync Gateway reported no stats for database {db_name!r}, "
                f"it reports: {', '.join(self.per_db) or 'none'}"
            )
        return self.per_db[db_name]
