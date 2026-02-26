import asyncio
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from cbltest import CBLPyTest
from cbltest.api.cbltestclass import CBLTestClass
from cbltest.api.error import CblEdgeServerBadResponseError

SCRIPT_DIR = str(Path(__file__).parent)


class TestTTLExpires(CBLTestClass):
    @pytest.mark.asyncio(loop_scope="session")
    async def test_ttl_5s(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        self.mark_test_step("Starting test to verify TTL feature")

        es_db_name = "db"
        edge_server = await cblpytest.edge_servers[0].configure_dataset(
            config_file=f"{SCRIPT_DIR}/config/test_edge_server_with_multiple_rest_clients.json",
        )

        self.mark_test_step("Creating a document with TTL of 5 seconds")
        doc = {
            "id": "ttl_doc",
            "channels": ["public"],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        response = await edge_server.put_document_with_id(
            doc, "ttl_doc", es_db_name, ttl=5
        )
        assert response is not None, "Failed to create document with TTL of 5 seconds"

        self.mark_test_step("Check if the document is present in the database")
        response = await edge_server.get_document(es_db_name, "ttl_doc")
        assert response is not None, "Document is not present in the database"

        self.mark_test_step("Checking if the document is expired after 5 seconds")
        time.sleep(5)
        with pytest.raises(CblEdgeServerBadResponseError):
            await edge_server.get_document(es_db_name, "ttl_doc")

    @pytest.mark.asyncio(loop_scope="session")
    async def test_expires_5s(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        self.mark_test_step("Starting test to verify Expires feature")

        es_db_name = "db"
        edge_server = await cblpytest.edge_servers[0].configure_dataset(
            config_file=f"{SCRIPT_DIR}/config/test_edge_server_with_multiple_rest_clients.json",
        )

        self.mark_test_step("Creating a document with Expires of 5 seconds")
        doc = {
            "id": "ttl_doc",
            "channels": ["public"],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        expires = datetime.now(timezone.utc) + timedelta(seconds=5)
        response = await edge_server.put_document_with_id(
            doc, "ttl_doc", es_db_name, expires=int(expires.timestamp())
        )
        assert response is not None, (
            "Failed to create document with Expires of 5 seconds"
        )

        self.mark_test_step("Check if the document is present in the database")
        response = await edge_server.get_document(es_db_name, "ttl_doc")
        assert response is not None, "Document is not present in the database"

        self.mark_test_step("Checking if the document is expired after 5 seconds")

        time.sleep(5)
        with pytest.raises(CblEdgeServerBadResponseError):
            await edge_server.get_document(es_db_name, "ttl_doc")

    @pytest.mark.asyncio(loop_scope="session")
    async def test_update_ttl(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        self.mark_test_step("Starting test to verify Update TTL feature")

        es_db_name = "db"
        edge_server = await cblpytest.edge_servers[0].configure_dataset(
            config_file=f"{SCRIPT_DIR}/config/test_edge_server_with_multiple_rest_clients.json",
        )

        self.mark_test_step("Creating a document with TTL of 30 seconds")
        doc = {
            "id": "ttl",
            "channels": ["public"],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        response = await edge_server.put_document_with_id(
            doc, "ttl", es_db_name, ttl=30
        )
        assert response is not None, "Failed to create document with TTL of 30 seconds"

        self.mark_test_step("Check if the document is present in the database")
        response = await edge_server.get_document(es_db_name, "ttl")
        assert response is not None, "Document is not present in the database"

        rev_id = response.get("rev")

        self.mark_test_step("Updating the TTL of the document to 5 seconds")

        updated_doc = {
            "id": "ttl",
            "channels": ["public"],
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "updated": "yes",
        }
        response = await edge_server.put_document_with_id(
            updated_doc, "ttl", es_db_name, rev=rev_id, ttl=5
        )
        assert response is not None, "Failed to update document with TTL of 5 seconds"

        self.mark_test_step("Check if the document is expired after 5 seconds")

        time.sleep(5)
        with pytest.raises(CblEdgeServerBadResponseError):
            await edge_server.get_document(es_db_name, "ttl")

    @pytest.mark.asyncio(loop_scope="session")
    async def test_ttl_expires(self, cblpytest: CBLPyTest, dataset_path: Path) -> None:
        self.mark_test_step(
            "Starting test to verify that with both ttl and expires provided, the lower value is used"
        )

        es_db_name = "db"
        edge_server = await cblpytest.edge_servers[0].configure_dataset(
            config_file=f"{SCRIPT_DIR}/config/test_edge_server_with_multiple_rest_clients.json",
        )

        self.mark_test_step(
            "Creating a document with TTL of 10 seconds and Expires of 30 seconds"
        )

        doc = {
            "id": "ttl_expires_doc1",
            "channels": ["public"],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        # Calculate expires as current timestamp + 30 seconds (Unix timestamp)
        expires_timestamp = int(time.time()) + 30

        response = await edge_server.put_document_with_id(
            doc, "ttl_expires_doc", es_db_name, ttl=10, expires=expires_timestamp
        )
        assert response is not None, "Failed to create document with TTL and expires"

        # Verify document exists immediately
        self.mark_test_step("Check if the document is present in the database")
        response = await edge_server.get_document(es_db_name, "ttl_expires_doc")
        assert response is not None, "Document is not present in the database"

        # Wait 10 seconds - document should expire (TTL=10s is lower than expires=30s, so TTL should take precedence)
        self.mark_test_step(
            "Waiting 10 seconds - document should expire based on TTL (lower value)"
        )
        time.sleep(10)

        self.mark_test_step(
            "Document expired after 10 seconds - TTL took precedence over expires"
        )
        with pytest.raises(CblEdgeServerBadResponseError):
            await edge_server.get_document(es_db_name, "ttl_expires_doc")

        self.mark_test_step(
            "Creating a document with TTL of 60 seconds and Expires of 10 seconds"
        )

        doc2 = {
            "id": "ttl_expires_doc2",
            "channels": ["public"],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        # Calculate expires as current timestamp + 10 seconds (Unix timestamp) - lower than TTL
        expires_timestamp2 = int(time.time()) + 10

        response2 = await edge_server.put_document_with_id(
            doc2, "ttl_expires_doc2", es_db_name, ttl=60, expires=expires_timestamp2
        )
        assert response2 is not None, "Failed to create document with TTL and expires"

        # Verify document exists immediately
        self.mark_test_step("Check if the document is present in the database")
        response2 = await edge_server.get_document(es_db_name, "ttl_expires_doc2")
        assert response2 is not None, "Document is not present in the database"

        # Wait 10 seconds - document should expire (expires=10s is lower than TTL=60s, so expires should take precedence)
        self.mark_test_step(
            "Waiting 10 seconds - document should expire based on expires (lower value)"
        )
        time.sleep(10)

        self.mark_test_step(
            "Document expired after 10 seconds - expires took precedence over TTL"
        )
        with pytest.raises(CblEdgeServerBadResponseError):
            await edge_server.get_document(es_db_name, "ttl_expires_doc2")

    @pytest.mark.asyncio(loop_scope="session")
    async def test_ttl_non_existent_document(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
        self.mark_test_step(
            "Starting test to verify TTL feature for non-existent document"
        )

        es_db_name = "db"
        edge_server = await cblpytest.edge_servers[0].configure_dataset(
            config_file=f"{SCRIPT_DIR}/config/test_edge_server_with_multiple_rest_clients.json",
        )

        self.mark_test_step(
            "Checking if updating TTL of a non-existent document returns 404"
        )

        with pytest.raises(CblEdgeServerBadResponseError):
            await edge_server.put_document_with_id(
                {"id": "ttl_doc"}, "ttl_doc", es_db_name, rev="1-1234567890", ttl=5
            )

    @pytest.mark.asyncio(loop_scope="session")
    async def test_bulk_documents_ttl(
        self, cblpytest: CBLPyTest, dataset_path: Path
    ) -> None:
        self.mark_test_step(
            "Starting test to see if bulk documents with TTL are deleted after the TTL expires"
        )

        es_db_name = "db"
        edge_server = await cblpytest.edge_servers[0].configure_dataset(
            config_file=f"{SCRIPT_DIR}/config/test_edge_server_with_multiple_rest_clients.json",
        )

        # Document distribution:
        # - 50 docs with 10s TTL
        # - 25 docs with 30s TTL
        # - 25 docs with 60s TTL

        self.mark_test_step("Creating documents with different TTLs")

        # Create all documents concurrently
        tasks = []
        task_ttl_map = []  # Track which TTL category each task belongs to

        # 50 docs with 10s TTL
        for doc_num in range(1, 51):
            doc_id = f"ttl_doc_{doc_num}"
            doc = {
                "id": doc_id,
                "channels": ["public"],
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "ttl": 10,
                "doc_num": doc_num,
            }
            tasks.append(
                edge_server.put_document_with_id(doc, doc_id, es_db_name, ttl=10)
            )
            task_ttl_map.append(10)

        # 25 docs with 30s TTL
        for doc_num in range(51, 76):
            doc_id = f"ttl_doc_{doc_num}"
            doc = {
                "id": doc_id,
                "channels": ["public"],
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "ttl": 30,
                "doc_num": doc_num,
            }
            tasks.append(
                edge_server.put_document_with_id(doc, doc_id, es_db_name, ttl=30)
            )
            task_ttl_map.append(30)

        # 25 docs with 60s TTL
        for doc_num in range(76, 101):
            doc_id = f"ttl_doc_{doc_num}"
            doc = {
                "id": doc_id,
                "channels": ["public"],
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "ttl": 60,
                "doc_num": doc_num,
            }
            tasks.append(
                edge_server.put_document_with_id(doc, doc_id, es_db_name, ttl=60)
            )
            task_ttl_map.append(60)

        # Execute all document creations concurrently
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Count successful creations by TTL category
        successful_10s = 0
        successful_30s = 0
        successful_60s = 0

        for i, result in enumerate(results):
            if not isinstance(result, Exception) and result is not None:
                ttl_category = task_ttl_map[i]
                if ttl_category == 10:
                    successful_10s += 1
                elif ttl_category == 30:
                    successful_30s += 1
                elif ttl_category == 60:
                    successful_60s += 1

        successful = successful_10s + successful_30s + successful_60s
        failed = len(results) - successful
        self.mark_test_step(
            f"Created {successful} documents with TTL ({successful_10s} @ 10s, {successful_30s} @ 30s, {successful_60s} @ 60s), {failed} failed"
        )

        # Verify initial count
        initial_response = await edge_server.get_all_documents(es_db_name)
        initial_count = len(initial_response.rows)
        self.mark_test_step(f"Initial document count: {initial_count}")
        assert initial_count == successful, (
            f"Expected {successful} documents, but found {initial_count}"
        )

        # Step 1: After 10s, check that docs with 30s and 60s TTL remain
        self.mark_test_step("Waiting 10 seconds - 10s TTL documents should expire")
        time.sleep(10)

        response_10s = await edge_server.get_all_documents(es_db_name)
        count_10s = len(response_10s.rows)
        expected_10s = successful_30s + successful_60s
        self.mark_test_step(
            f"Document count after 10 seconds: {count_10s} (expected {expected_10s})"
        )
        assert count_10s == expected_10s, (
            f"After 10s: Expected {expected_10s} documents (30s and 60s TTL), but found {count_10s}"
        )

        # Step 2: After 30s total, check that docs with 60s TTL remain
        self.mark_test_step(
            "Waiting additional 20 seconds (30s total) - 30s TTL documents should expire"
        )
        time.sleep(20)

        response_30s = await edge_server.get_all_documents(es_db_name)
        count_30s = len(response_30s.rows)
        expected_30s = successful_60s
        self.mark_test_step(
            f"Document count after 30 seconds: {count_30s} (expected {expected_30s})"
        )
        assert count_30s == expected_30s, (
            f"After 30s: Expected {expected_30s} documents (60s TTL), but found {count_30s}"
        )

        # Step 3: After 60s total, check that 0 docs remain
        self.mark_test_step(
            "Waiting additional 30 seconds (60s total) - 60s TTL documents should expire"
        )
        time.sleep(30)

        response_60s = await edge_server.get_all_documents(es_db_name)
        count_60s = len(response_60s.rows)
        expected_60s = 0
        self.mark_test_step(
            f"Document count after 60 seconds: {count_60s} (expected {expected_60s})"
        )
        assert count_60s == expected_60s, (
            f"After 60s: Expected {expected_60s} documents, but found {count_60s}"
        )
