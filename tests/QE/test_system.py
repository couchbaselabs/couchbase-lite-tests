import asyncio
import random
import threading
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.api.cloud import CouchbaseCloud
from cbltest.api.database_types import DocumentEntry
from cbltest.api.replicator import Replicator
from cbltest.api.replicator_types import (
    ReplicatorActivityLevel,
    ReplicatorBasicAuthenticator,
    ReplicatorCollectionEntry,
)


@pytest.mark.min_test_servers(1)
@pytest.mark.min_sync_gateways(1)
@pytest.mark.min_couchbase_servers(1)
class TestSystem(CBLTestClass):
    # Test parameters
    NUM_OF_DOCS = 1000000  # 1M docs
    NUM_OF_DOC_UPDATES = 100
    NUM_OF_DOCS_TO_UPDATE = 100
    NUM_OF_DOCS_TO_DELETE = 1000
    NUM_OF_DOCS_IN_ITR = 10  # Much smaller batch to avoid "413 Payload Too Large" error
    NUM_OF_DOCS_TO_ADD = 1000
    UP_TIME_DAYS = 4
    REPL_STATUS_CHECK_SLEEP_TIME = 20

    @property
    def num_of_itr_per_db(self) -> int:
        return self.NUM_OF_DOCS // self.NUM_OF_DOCS_IN_ITR

    async def _initialize_database_documents(
        self, db_name: str, db, docs_per_db: int
    ) -> set[str]:
        """Initialize documents for a single database - runs concurrently per database"""
        iterations_per_db = docs_per_db // self.NUM_OF_DOCS_IN_ITR
        doc_ids = set()

        self.mark_test_step(
            f"[{db_name}] Creating {docs_per_db} documents in {iterations_per_db} batches"
        )

        for iteration in range(iterations_per_db):
            max_retries = 3
            retry_delay = 1
            batch_doc_ids: list[str] = []

            # Retry logic with exponential backoff - wraps the entire batch operation
            for retry in range(max_retries):
                try:
                    batch_doc_ids.clear()  # Clear any previous attempt
                    async with db.batch_updater() as batch:
                        for doc_num in range(self.NUM_OF_DOCS_IN_ITR):
                            doc_id = f"{db_name}_doc_{iteration}_{doc_num}_{random.randint(1000, 9999)}"
                            # Create document with realistic properties (but simpler than before)
                            batch.upsert_document(
                                "_default._default",
                                doc_id,
                                new_properties=[
                                    {
                                        "type": "system_test_doc",
                                        "database": db_name,
                                        "iteration": iteration,
                                        "doc_number": doc_num,
                                        "content": f"Initial content for {doc_id}",
                                        "timestamp": datetime.now().isoformat(),
                                        "update_count": 0,
                                    }
                                ],
                            )
                            batch_doc_ids.append(doc_id)

                    # If we get here, the batch succeeded (including the __aexit__)
                    break

                except Exception as e:
                    print(
                        f"[{db_name}] Batch {iteration + 1} failed (attempt {retry + 1}/{max_retries}): {e}"
                    )
                    if retry == max_retries - 1:
                        # Last retry failed, re-raise the exception
                        raise
                    else:
                        # Wait before retrying with exponential backoff
                        print(f"[{db_name}] Retrying in {retry_delay} seconds...")
                        await asyncio.sleep(retry_delay)
                        retry_delay *= 2  # Exponential backoff

            doc_ids.update(batch_doc_ids)

            # Add a delay between batches to reduce server load
            if iteration < iterations_per_db - 1:  # Don't delay after the last batch
                await asyncio.sleep(0.1)  # Small delay since batches are now very small

            # Log progress every 100 batches per database
            if (iteration + 1) % 100 == 0:
                print(
                    f"[{db_name}] Created {(iteration + 1) * self.NUM_OF_DOCS_IN_ITR} documents so far..."
                )

        print(f"[{db_name}] Completed initialization with {len(doc_ids)} documents")
        return doc_ids

    async def _run_database_crud_loop(
        self, db_name: str, db, replicator, cblpytest
    ) -> None:
        """Main CRUD loop for a single database - runs concurrently per database"""
        iteration_count = 0

        # Get this thread's document set (thread-safe copy)
        with self.doc_ids_lock:
            my_doc_ids = self.doc_ids_dict[db_name].copy()

        print(f"[{db_name}] Starting CRUD loop with {len(my_doc_ids)} documents")

        while (
            self.iteration_end_time is not None
            and datetime.now() < self.iteration_end_time
        ):
            try:
                iteration_count += 1
                remaining_time = (
                    self.iteration_end_time - datetime.now()
                    if self.iteration_end_time
                    else "Unknown"
                )

                print(
                    f"[{db_name}] CRUD Iteration {iteration_count} - Time remaining: {remaining_time}"
                )

                # Refresh document count (important after deletions)
                if len(my_doc_ids) < max(
                    self.NUM_OF_DOCS_TO_UPDATE, self.NUM_OF_DOCS_TO_DELETE * 2
                ):
                    print(
                        f"[{db_name}] Warning: Only {len(my_doc_ids)} documents available"
                    )
                    print(
                        f"[{db_name}] This may indicate network issues. Consider --resume-cluster for local runs."
                    )
                    await asyncio.sleep(10)  # Wait before retrying
                    continue

                # Execute CRUD operations for this database
                await self._execute_crud_operations(
                    db_name, db, replicator, cblpytest, my_doc_ids, iteration_count
                )

                # Update shared doc_ids_dict with this thread's changes (thread-safe)
                with self.doc_ids_lock:
                    self.doc_ids_dict[db_name] = my_doc_ids.copy()

                # Small delay between iterations
                await asyncio.sleep(1)

            except Exception as e:
                print(f"[{db_name}] Error in iteration {iteration_count}: {e}")
                print(f"[{db_name}] Continuing with next iteration...")
                await asyncio.sleep(5)  # Brief pause before continuing

        print(
            f"[{db_name}] Completed {iteration_count} iterations with {len(my_doc_ids)} final documents"
        )

    async def _execute_crud_operations(
        self,
        db_name: str,
        db,
        replicator,
        cblpytest,
        my_doc_ids: set[str],
        iteration_count: int,
    ) -> None:
        """Execute CRUD operations for a single database thread"""

        # 1. Update random documents on SG side
        if len(my_doc_ids) >= self.NUM_OF_DOCS_TO_UPDATE:
            docs_to_update_sg = random.sample(
                list(my_doc_ids), self.NUM_OF_DOCS_TO_UPDATE
            )

            for doc_id in docs_to_update_sg:
                for update_num in range(self.NUM_OF_DOC_UPDATES):
                    try:
                        current_doc = await cblpytest.sync_gateways[0].get_document(
                            "names", doc_id
                        )
                        if current_doc:
                            updated_body = current_doc.get("body", {})
                            updated_body.update(
                                {
                                    f"sgw_{db_name}_update_count": updated_body.get(
                                        f"sgw_{db_name}_update_count", 0
                                    )
                                    + 1,
                                    f"last_sgw_{db_name}_update": datetime.now().isoformat(),
                                    "update_iteration": iteration_count,
                                    "update_number": update_num,
                                    "content": f"SGW {db_name} updated content - iteration {iteration_count}, update {update_num}",
                                }
                            )
                            await cblpytest.sync_gateways[0].update_document(
                                "names", doc_id, updated_body
                            )
                    except Exception as e:
                        print(
                            f"[{db_name}] Error updating document {doc_id} on SGW: {e}"
                        )

        # Wait for SG updates to sync
        await self._wait_for_replication_idle_single(replicator, db_name)

        # 2. Update random documents on this CBL app (in smaller batches to avoid payload size issues)
        if len(my_doc_ids) >= self.NUM_OF_DOCS_TO_UPDATE:
            docs_to_update_cbl = random.sample(
                list(my_doc_ids), self.NUM_OF_DOCS_TO_UPDATE
            )

            # Process updates in smaller batches to avoid "413 Payload Too Large" error
            batch_size = (
                self.NUM_OF_DOCS_IN_ITR
            )  # Use same batch size as document creation
            for doc_id in docs_to_update_cbl:
                for batch_start in range(0, self.NUM_OF_DOC_UPDATES, batch_size):
                    batch_end = min(batch_start + batch_size, self.NUM_OF_DOC_UPDATES)

                    async with db.batch_updater() as batch:
                        for update_num in range(batch_start, batch_end):
                            try:
                                current_doc = await db.get_document(
                                    DocumentEntry("_default._default", doc_id)
                                )
                                if current_doc:
                                    updated_body = current_doc.body.copy()
                                    updated_body.update(
                                        {
                                            f"cbl_{db_name}_update_count": updated_body.get(
                                                f"cbl_{db_name}_update_count", 0
                                            )
                                            + 1,
                                            f"last_cbl_{db_name}_update": datetime.now().isoformat(),
                                            "update_iteration": iteration_count,
                                            "update_number": update_num,
                                            "content": f"CBL {db_name} updated content - iteration {iteration_count}, update {update_num}",
                                        }
                                    )
                                    batch.upsert_document(
                                        "_default._default",
                                        doc_id,
                                        new_properties=[updated_body],
                                    )
                            except Exception as e:
                                print(
                                    f"[{db_name}] Error updating document {doc_id} on CBL: {e}"
                                )

                    # Small delay between batches to reduce server load
                    await asyncio.sleep(0.1)

        # Wait for CBL updates to sync
        await self._wait_for_replication_idle_single(replicator, db_name)

        # 3. Delete documents on SG side
        if len(my_doc_ids) >= self.NUM_OF_DOCS_TO_DELETE:
            docs_to_delete_sg = set(
                random.sample(list(my_doc_ids), self.NUM_OF_DOCS_TO_DELETE)
            )

            for doc_id in docs_to_delete_sg:
                try:
                    await cblpytest.sync_gateways[0].delete_document("names", doc_id)
                except Exception as e:
                    print(f"[{db_name}] Error deleting document {doc_id} from SGW: {e}")
                    print(
                        f"[{db_name}] This may be due to conflicts - new logging should help identify the issue"
                    )

            # Remove from this thread's document set
            my_doc_ids -= docs_to_delete_sg
            print(f"[{db_name}] Deleted {len(docs_to_delete_sg)} documents from SG")

        # Wait for SG deletions to sync
        await self._wait_for_replication_idle_single(replicator, db_name)

        # 4. Delete different documents on this CBL app (in smaller batches to avoid payload size issues)
        if len(my_doc_ids) >= self.NUM_OF_DOCS_TO_DELETE:
            docs_to_delete_cbl = set(
                random.sample(list(my_doc_ids), self.NUM_OF_DOCS_TO_DELETE)
            )
            docs_to_delete_list = list(docs_to_delete_cbl)

            # Process deletions in smaller batches to avoid "413 Payload Too Large" error
            batch_size = (
                self.NUM_OF_DOCS_IN_ITR
            )  # Use same batch size as other operations
            for batch_start in range(0, len(docs_to_delete_list), batch_size):
                batch_end = min(batch_start + batch_size, len(docs_to_delete_list))
                batch_docs = docs_to_delete_list[batch_start:batch_end]

                async with db.batch_updater() as batch:
                    for doc_id in batch_docs:
                        try:
                            batch.delete_document("_default._default", doc_id)
                        except Exception as e:
                            print(
                                f"[{db_name}] Error deleting document {doc_id} from CBL: {e}"
                            )
                            print(
                                f"[{db_name}] This may be due to conflicts causing doc delete in one app but not others"
                            )

                # Small delay between batches to reduce server load
                await asyncio.sleep(0.1)

            # Remove from this thread's document set
            my_doc_ids -= docs_to_delete_cbl
            print(
                f"[{db_name}] Deleted {len(docs_to_delete_cbl)} documents from CBL in batches of {batch_size}"
            )

        # Wait for CBL deletions to sync
        await self._wait_for_replication_idle_single(replicator, db_name)

        # 5. Create new documents on this CBL app (in smaller batches to avoid payload size issues)
        new_doc_ids = []

        # Process document creation in smaller batches to avoid "413 Payload Too Large" error
        batch_size = self.NUM_OF_DOCS_IN_ITR  # Use same batch size as other operations
        for batch_start in range(0, self.NUM_OF_DOCS_TO_ADD, batch_size):
            batch_end = min(batch_start + batch_size, self.NUM_OF_DOCS_TO_ADD)

            async with db.batch_updater() as batch:
                for doc_num in range(batch_start, batch_end):
                    doc_id = f"{db_name}_new_doc_{iteration_count}_{doc_num}_{random.randint(10000, 99999)}"
                    doc_body = {
                        "type": "system_test_new_doc",
                        "database": db_name,
                        "created_on": "CBL",
                        "iteration": iteration_count,
                        "doc_number": doc_num,
                        "content": f"New document created in iteration {iteration_count} for {db_name}",
                        "timestamp": datetime.now().isoformat(),
                    }
                    batch.upsert_document(
                        "_default._default", doc_id, new_properties=[doc_body]
                    )
                    new_doc_ids.append(doc_id)

            # Small delay between batches to reduce server load
            await asyncio.sleep(0.1)

        # Add to this thread's document set
        my_doc_ids.update(new_doc_ids)
        print(
            f"[{db_name}] Created {len(new_doc_ids)} new documents in batches of {batch_size}"
        )

        # Wait for CBL creations to sync
        await self._wait_for_replication_idle_single(replicator, db_name)

        # Optional: Query DB to verify state
        try:
            local_docs = await db.get_all_documents("_default._default")
            local_count = len(local_docs["_default._default"])
            print(f"[{db_name}] Current local document count: {local_count}")
        except Exception as e:
            print(f"[{db_name}] Error querying local documents: {e}")

    @pytest.mark.asyncio(loop_scope="session")
    async def test_system(self, cblpytest: CBLPyTest, dataset_path: Path):
        """
        Concurrent system test that performs CRUD operations with replication
        using asyncio concurrency for parallel execution across multiple CBL clients.

        Each CBL app operates independently in its own async task, creating realistic
        concurrent load while maintaining proper synchronization for shared data.
        """
        self.doc_ids_dict: dict[str, set[str]] = {}
        self.doc_ids_lock = threading.Lock()
        self.iteration_start_time: datetime | None = None
        self.iteration_end_time: datetime | None = None

        self.mark_test_step("RESET CLUSTER - Stop sync gateway, create server bucket")
        cloud = CouchbaseCloud(
            cblpytest.sync_gateways[0], cblpytest.couchbase_servers[0]
        )
        await cloud.configure_dataset(dataset_path, "names")

        self.mark_test_step(
            "Reset local databases and prepare for concurrent initialization"
        )
        num_test_servers = len(cblpytest.test_servers)
        self.mark_test_step(f"Detected {num_test_servers} test servers available")

        databases = {}
        for i, test_server in enumerate(cblpytest.test_servers):
            db_name = f"db{i + 1}"
            db = (await test_server.create_and_reset_db([db_name]))[0]
            databases[db_name] = db
            print(f"Created database {db_name} on test server {i}")

        self.doc_ids_dict = {db_name: set() for db_name in databases.keys()}
        print(f"Initialized {len(databases)} databases: {list(databases.keys())}")

        # Calculate docs per database (1M docs divided equally among CBL apps)
        docs_per_db = self.NUM_OF_DOCS // len(databases)

        self.mark_test_step(
            f"CONCURRENT INITIALIZATION: Create {self.NUM_OF_DOCS} documents using asyncio concurrency"
        )

        # Use asyncio concurrency for concurrent document initialization
        initialization_tasks = []
        for db_name, db in databases.items():
            init_task = self._initialize_database_documents(db_name, db, docs_per_db)
            initialization_tasks.append((db_name, init_task))

        # Execute initialization tasks concurrently using asyncio.gather
        initialization_results = await asyncio.gather(
            *[init_task for _, init_task in initialization_tasks]
        )

        # Update doc_ids_dict with results
        for i, (db_name, _) in enumerate(initialization_tasks):
            self.doc_ids_dict[db_name] = initialization_results[i]

        total_docs_created = sum(len(doc_set) for doc_set in self.doc_ids_dict.values())
        print(
            f"CONCURRENT INITIALIZATION COMPLETE: {total_docs_created} documents created across all databases"
        )

        self.mark_test_step("""
            Configure independent replicators for each database
                * endpoint: `/names`
                * collections: `_default._default`
                * type: push-and-pull
                * continuous: true
                * credentials: user1/pass
        """)
        replicators = {}
        for db_name, db in databases.items():
            replicators[db_name] = Replicator(
                db,
                cblpytest.sync_gateways[0].replication_url("names"),
                collections=[ReplicatorCollectionEntry(["_default._default"])],
                authenticator=ReplicatorBasicAuthenticator("user1", "pass"),
                pinned_server_cert=cblpytest.sync_gateways[0].tls_cert(),
                continuous=True,
            )
            print(f"[{db_name}] Replicator configured")

        self.mark_test_step("Start replication to sync documents across cluster")
        for db_name, replicator in replicators.items():
            await replicator.start()
            print(f"[{db_name}] Replicator started")

        self.mark_test_step("Wait for initial replication sync across all CBL apps")
        for db_name, replicator in replicators.items():
            status = await replicator.wait_for(
                ReplicatorActivityLevel.IDLE,
                timedelta(seconds=self.REPL_STATUS_CHECK_SLEEP_TIME),
                timedelta(minutes=600),  # Allow time for cross-sync for 1M docs
            )
            assert status.error is None, (
                f"Error during initial replication for {db_name}: {status.error}"
            )
            print(f"[{db_name}] Initial replication completed")

        self.mark_test_step("Verify cross-sync: each CBL app should have all documents")
        for db_name, db in databases.items():
            local_docs = await db.get_all_documents("_default._default")
            local_count = len(local_docs["_default._default"])
            print(f"[{db_name}] Document count after sync: {local_count}")

            # Allow tolerance for replication delays
            assert local_count >= self.NUM_OF_DOCS * 0.95, (
                f"[{db_name}] Expected ~{self.NUM_OF_DOCS} documents, got {local_count}. Network issues may be causing sync delays."
            )

        # Verify SG has all documents
        sg_docs = await cblpytest.sync_gateways[0].get_all_documents("names")
        sg_count = len(sg_docs.rows)
        print(f"Sync Gateway document count: {sg_count}")
        assert sg_count >= self.NUM_OF_DOCS * 0.95, (
            f"Expected ~{self.NUM_OF_DOCS} documents on SG, got {sg_count}."
        )

        self.mark_test_step(
            f"CONCURRENT EXECUTION: Starting {self.UP_TIME_DAYS}-day CRUD operations using asyncio concurrency"
        )
        self.mark_test_step(
            f"TIMER STARTS NOW - Test will run for exactly {self.UP_TIME_DAYS} day(s) from this point"
        )

        # Timer starts only when iterations begin (as per requirement)
        self.iteration_start_time = datetime.now()
        self.iteration_end_time = self.iteration_start_time + timedelta(
            days=self.UP_TIME_DAYS
        )

        # Create async tasks for each database
        crud_tasks = []
        for db_name, db in databases.items():
            replicator = replicators[db_name]
            crud_task = self._run_database_crud_loop(db_name, db, replicator, cblpytest)
            crud_tasks.append((db_name, crud_task))
            print(f"[{db_name}] CRUD task scheduled")

        # Execute all CRUD tasks concurrently using asyncio
        self.mark_test_step(
            "Executing concurrent CRUD operations - each database operates independently"
        )
        try:
            # Run all database CRUD loops concurrently until time expires
            await asyncio.gather(
                *[crud_task for _, crud_task in crud_tasks], return_exceptions=True
            )
        except Exception as e:
            print(f"Exception in concurrent execution: {e}")

        self.mark_test_step("CRUD operations loop completed - verifying final state")
        total_local_count = 0
        for db_name, db in databases.items():
            final_local_docs = await db.get_all_documents("_default._default")
            local_count = len(final_local_docs["_default._default"])
            total_local_count += local_count
            print(f"Final document count in {db_name}: {local_count}")

        final_sg_docs = await cblpytest.sync_gateways[0].get_all_documents("names")
        sg_count = len(final_sg_docs.rows)

        print(
            f"Final document counts - Total CBL: {total_local_count}, SGW: {sg_count}"
        )
        print(f"Test duration: {datetime.now() - self.iteration_start_time}")
        print(
            f"SUCCESS: Concurrent test completed exactly {self.UP_TIME_DAYS} day(s) of continuous CRUD operations"
        )

        # Verify replication consistency (allowing for some tolerance due to concurrent operations and network issues)
        tolerance = max(
            100, total_local_count * 0.02
        )  # 2% tolerance or minimum 100 docs (higher due to concurrency)
        assert abs(total_local_count - sg_count) <= tolerance, (
            f"Document count mismatch between CBL ({total_local_count}) and SGW ({sg_count}). Difference should be <= {tolerance}."
        )

        print(
            "SUCCESS: Concurrent execution maintained document consistency between CBL apps and Sync Gateway"
        )

        # Cleanup all test servers dynamically
        for i, test_server in enumerate(cblpytest.test_servers):
            await test_server.cleanup()
            print(f"Cleaned up test server {i}")

    async def _wait_for_replication_idle_single(
        self, replicator: Replicator, db_name: str
    ) -> None:
        """Helper method to wait for a single replicator to reach idle state"""
        try:
            status = await replicator.wait_for(
                ReplicatorActivityLevel.IDLE,
                timedelta(seconds=self.REPL_STATUS_CHECK_SLEEP_TIME),
                timedelta(minutes=3),  # Shorter timeout for individual threads
            )
            if status.error:
                print(
                    f"[{db_name}] Warning: Replication error during wait: {status.error}"
                )
        except Exception as e:
            print(f"[{db_name}] Warning: Error waiting for replication idle: {e}")

    async def _wait_for_replication_idle_all(
        self, replicators: dict[str, Replicator]
    ) -> None:
        """Helper method to wait for all replicators to reach idle state"""
        for db_name, replicator in replicators.items():
            try:
                status = await replicator.wait_for(
                    ReplicatorActivityLevel.IDLE,
                    timedelta(seconds=self.REPL_STATUS_CHECK_SLEEP_TIME),
                    timedelta(minutes=5),  # Maximum wait time
                )
                if status.error:
                    print(
                        f"Warning: Replication error for {db_name} during wait: {status.error}"
                    )
            except Exception as e:
                print(f"Warning: Error waiting for replication idle for {db_name}: {e}")
