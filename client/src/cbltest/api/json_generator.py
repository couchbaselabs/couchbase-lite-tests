import random
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Dict, List


class JSONGenerator:
    """
       Utility class to generate and update reproducible JSON documents for testing.

       Usage:
           gen = JSONGenerator(size=1000, format="json")
           docs = gen.generate_all_documents()
           updated_docs = gen.update_all_documents(docs)

       Parameters:
           seed (int, optional): Random seed for reproducibility (default: random int).
           size (int, optional): Number of documents to generate (default: 60000).
           format (str, optional): Output format - "json" (dict) or "key-value" (list of dicts/documents).
                                 To insert/update in CB-server/SGW/ Edge-server : use format "json".
                                 To insert into test-server use format "key-value" .
       """
    def __init__(self, seed=random.randint(0, sys.maxsize), size=60000, format="json"):
        self.seed = seed
        self.size = size
        self.format = format

    def generate_document(self, doc_id: str) -> Dict[str, Any]:
        """Generate a single JSON document with reproducible random data"""
        random.seed(self.seed + int(doc_id.split("-")[0], 16))
        if self.format == "json":
            return {
                doc_id: {
                    "data": {
                        "temperature": random.uniform(-20, 40),
                        "humidity": random.randint(0, 100),
                        "status": random.choice(["active", "inactive", "maintenance"]),
                    },
                    "metadata": {
                        "version": 1,
                        "created_at": int(time.time()),
                        "modified_at": int(time.time()),
                    },
                }
            }
        else:
            return {
                doc_id: [{
                    "data": {
                        "temperature": random.uniform(-20, 40),
                        "humidity": random.randint(0, 100),
                        "status": random.choice(["active", "inactive", "maintenance"]),
                    }},
                    {"metadata": {
                        "version": 1,
                        "created_at": int(time.time()),
                        "modified_at": int(time.time()),
                    }}
                ]
            }

    def update_document(self, doc: Any, doc_id: str) -> Dict[str, Any]:
        """Update a document with reproducible modifications"""
        offset = int(doc_id.split("-")[0], 16)
        random.seed(self.seed + offset)
        if self.format == "json":
            doc["data"]["temperature"] += random.uniform(-5, 5)
            doc["data"]["humidity"] = (doc["data"]["humidity"] + random.randint(-10, 10)) % 100
            doc["data"]["status"] = random.choice(["active", "inactive", "maintenance"])
            doc["metadata"]["version"] = doc["metadata"]["version"] + 1
            doc["metadata"]["modified_at"] = int(time.time())

        else:
            doc[0]["data"] = {
                "temperature": random.uniform(-20, 40),
                "humidity": random.randint(0, 100),
                "status": random.choice(["active", "inactive", "maintenance"]),
            }
            doc[1]["metadata"]["version"] = doc[1]["metadata"]["version"] + 1
            doc[1]["metadata"]["modified_at"] = int(time.time())
        return {doc_id: doc}

    def batch_process(
            self,
            process_fn: Callable,
            items_ids: List[Any],
            items_doc: Dict[str, Any] = None,
            batch_size: int = 1000
    ) -> Dict[Any, Any]:
        """Generic batch processing function with threading"""
        results = {}

        def process_batch(batch):
            result = {}
            for item in batch:
                output = process_fn(items_doc[item], item) if items_doc is not None else process_fn(item)
                result.update(output)
            return result

        with ThreadPoolExecutor() as executor:
            futures = [
                executor.submit(process_batch, items_ids[i:i + batch_size])
                for i in range(0, len(items_ids), batch_size)
            ]
            for future in futures:
                results.update(future.result())

        return results

    def generate_all_documents(self, size=None) -> Dict[str, Any]:
        """Generate all documents using parallel processing"""
        if size is None:
            size = self.size
        print(f"Generating {size} documents...")
        start = time.time()

        doc_ids = [str(uuid.uuid4()) for _ in range(size)]
        documents = self.batch_process(
            self.generate_document,
            doc_ids
        )

        print(f"Generated {len(documents)} documents in {time.time() - start:.2f}s")
        return documents

    def update_all_documents(self, documents: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        """Update all documents with consistent modifications"""
        print("Updating documents...")
        start = time.time()

        doc_ids = list(documents.keys())
        updated = self.batch_process(
            self.update_document,
            doc_ids,
            documents
        )

        print(f"Updated {len(updated)} documents in {time.time() - start:.2f}s")
        return updated


