import random
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List


class JSONGenerator:
    def __init__(self, seed=random.randint(0, sys.maxsize), size=60000):
        self.seed = seed
        self.size = size

    def generate_document(self, doc_id: str) -> Dict[str, Any]:
        """Generate a single JSON document with reproducible random data"""
        random.seed(self.seed + int(doc_id.split("-")[0], 16))
        return {
            "_id": doc_id,
            "data": {
                "temperature": random.uniform(-20, 40),
                "humidity": random.randint(0, 100),
                "status": random.choice(["active", "inactive", "maintenance"]),
            },
            "metadata": {
                "version": "1.0",
                "created_at": int(time.time()),
                "modified_at": int(time.time()),
            },
        }

    def update_document(self, doc: Dict[str, Any]) -> Dict[str, Any]:
        """Update a document with reproducible modifications"""
        try:
            offset = int(doc["_id"].split("-")[0], 16)
        except KeyError:
            offset = doc["_rev"][0]
        random.seed(self.seed + offset)

        # Modify existing fields
        doc["data"]["temperature"] += random.uniform(-5, 5)
        doc["data"]["humidity"] = (
            doc["data"]["humidity"] + random.randint(-10, 10)
        ) % 100
        doc["data"]["status"] = random.choice(["active", "inactive", "maintenance"])

        # Update metadata
        doc["metadata"]["version"] = "2.0"
        doc["metadata"]["modified_at"] = int(time.time())
        return doc

    def batch_process(
        self, process_fn: callable, items: List[Any], batch_size: int = 1000
    ) -> List[Any]:
        """Generic batch processing function with threading"""
        results = []
        with ThreadPoolExecutor() as executor:
            futures = []
            for i in range(0, len(items), batch_size):
                batch = items[i : i + batch_size]

                futures.append(
                    executor.submit(lambda b: [process_fn(item) for item in b], batch)
                )

            for future in futures:
                results.extend(future.result())

        return results

    def generate_all_documents(self) -> List[Dict]:
        """Generate all documents using parallel processing"""
        print(f"Generating {self.size} documents...")
        start = time.time()

        documents = self.batch_process(
            lambda doc_id: self.generate_document(str(uuid.uuid4())), [None] * self.size
        )

        print(f"Generated {len(documents)} documents in {time.time() - start:.2f}s")
        return documents

    def update_all_documents(self, documents: List[Dict]) -> List[Dict]:
        """Update all documents with consistent modifications"""
        print("Updating documents...")
        start = time.time()

        updated = self.batch_process(self.update_document, documents)

        print(f"Updated {len(updated)} documents in {time.time() - start:.2f}s")
        return updated
