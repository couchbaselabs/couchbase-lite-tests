import asyncio
import json
import time
from typing import Dict, List, Optional

from cbltest.api.edgeserver import BulkDocOperation, EdgeServer
from cbltest.api.error import CblEdgeServerBadResponseError
from cbltest.api.remoteshell import RemoteShellConnection
from cbltest.api.syncgateway import AllDocumentsResponse, RemoteDocument


class HTTPClient:
    def __init__(
        self,
        vm_ip: str,
        edge_server: EdgeServer,
        client_id: int = 0,
        user: str = "root",
        password: str = "couchbase",
    ):
        self.client_id = client_id
        self.vm_ip = vm_ip
        self.user = user
        self.password = password
        self.edge_server = edge_server
        self.remote_shell = RemoteShellConnection(
            vm_ip, username=user, password=password
        )

    async def connect(self):
        await self.remote_shell.connect()

    async def get_version(self):
        curl = await self.edge_server.get_version(curl=True)
        response = await self.remote_shell.run_command(curl)
        try:
            response_dict = json.loads(response)
            if "error" in response_dict:
                raise CblEdgeServerBadResponseError(
                    500, f"Get version had error '{response_dict['reason']}'"
                )
            return response_dict
        except Exception as e:
            raise CblEdgeServerBadResponseError(
                500, f"Get version from edge server had error '{str(e)}'"
            )

    async def get_all_documents(
        self,
        db_name: str,
        scope: str = "",
        collection: str = "",
        descending=False,
        endkey=None,
        keys=None,
        startkey=None,
    ):
        curl = await self.edge_server.get_all_documents(
            db_name,
            scope,
            collection,
            curl=True,
            descending=descending,
            endkey=endkey,
            keys=keys,
            startkey=startkey,
        )
        response = await self.remote_shell.run_command(curl)
        try:
            response_dict = json.loads(response)
            if "error" in response_dict:
                raise CblEdgeServerBadResponseError(
                    500, f"Get all doc had error '{response_dict['reason']}'"
                )
            return AllDocumentsResponse(response_dict)
        except Exception as e:
            raise CblEdgeServerBadResponseError(
                500, f"Get all doc from edge server had error '{str(e)}', {response}"
            )

    async def delete_document(
        self,
        doc_id: str,
        revid: str,
        db_name: str,
        scope: str = "",
        collection: str = "",
        expires: int = 0,
        ttl: int = 0
    ):
        curl = await self.edge_server.delete_document(
            doc_id, revid, db_name, scope, collection, curl=True, expires=expires, ttl=ttl
        )
        response = await self.remote_shell.run_command(curl)
        try:
            response_dict = json.loads(response)
            if "error" in response_dict:
                raise CblEdgeServerBadResponseError(
                    500, f"Delete document had error '{response_dict['reason']}'"
                )
            return response_dict
        except Exception:
            raise CblEdgeServerBadResponseError(
                500, f"Delete document from edge server had error '{response}'"
            )

    async def get_document(
        self,
        db_name: str,
        doc_id: str,
        scope: str = "",
        collection: str = "",
        revid: Optional[str] = None,
    ):
        curl = await self.edge_server.get_document(
            db_name, doc_id, scope, collection, curl=True, revid=revid
        )
        print(curl)
        response = await self.remote_shell.run_command(curl)
        try:
            response_dict = json.loads(response)
            if "error" in response_dict:
                raise CblEdgeServerBadResponseError(
                    500, f"Get document had error '{response_dict['reason']}'"
                )
            return RemoteDocument(response_dict)
        except Exception:
            raise CblEdgeServerBadResponseError(
                500, f"Get document from edge server had error '{response}'"
            )

    async def get_all_dbs(self):
        curl = await self.edge_server.get_all_dbs(curl=True)
        response = await self.remote_shell.run_command(curl)
        try:
            response_list = json.loads(response)
            return response_list
        except Exception as e:
            raise CblEdgeServerBadResponseError(
                500,
                f"Get all databases from edge server had error '{response}', error: {e}",
            )

    async def get_active_tasks(self):
        curl = await self.edge_server.get_active_tasks(curl=True)
        response = await self.remote_shell.run_command(curl)
        try:
            response_dict = json.loads(response)
            if "error" in response_dict:
                raise CblEdgeServerBadResponseError(
                    500, f"Get active tasks had error '{response_dict['reason']}'"
                )
            return response_dict
        except Exception:
            raise CblEdgeServerBadResponseError(
                500, f"Get active tasks from edge server had error '{response}'"
            )

    async def get_db_info(self, db_name: str, scope: str = "", collection: str = ""):
        curl = await self.edge_server.get_db_info(db_name, scope, collection, curl=True)
        response = await self.remote_shell.run_command(curl)
        try:
            response_dict = json.loads(response)
            if "error" in response_dict:
                raise CblEdgeServerBadResponseError(
                    500, f"Get database had error '{response_dict['reason']}'"
                )
            return response_dict
        except Exception:
            raise CblEdgeServerBadResponseError(
                500, f"Get database info from edge server had error '{response}'"
            )

    async def start_replication(
        self,
        source: str,
        target: str,
        user: str,
        password: str,
        bidirectional: bool,
        continuous: bool,
        collections: Optional[List[str]] = None,
        channels: Optional[List[str]] = None,
        doc_ids: Optional[List[str]] = None,
        headers: Optional[Dict[str, str]] = None,
        trusted_root_certs: Optional[str] = None,
        pinned_cert: Optional[str] = None,
        session_cookie: Optional[str] = None,
        openid_token: Optional[str] = None,
        tls_client_cert: Optional[str] = None,
        tls_client_cert_key: Optional[str] = None,
    ):
        curl = await self.edge_server.start_replication(
            source,
            target,
            user,
            password,
            bidirectional,
            continuous,
            collections,
            channels,
            doc_ids,
            headers,
            trusted_root_certs,
            pinned_cert,
            session_cookie,
            openid_token,
            tls_client_cert,
            tls_client_cert_key,
            curl=True,
        )
        response = await self.remote_shell.run_command(curl)
        try:
            response_dict = json.loads(response)
            if "error" in response_dict:
                raise CblEdgeServerBadResponseError(
                    500, f"Start replication had error '{response_dict['reason']}'"
                )
            return response_dict.get("session_id")
        except Exception:
            raise CblEdgeServerBadResponseError(
                500, f"Start replication with edge server had error '{response}'"
            )

    async def replication_status(self, replicator_id: str):
        curl = await self.edge_server.replication_status(replicator_id, curl=True)
        response = await self.remote_shell.run_command(curl)
        try:
            response_dict = json.loads(response)
            if "error" in response_dict:
                raise CblEdgeServerBadResponseError(
                    500, f"Adhoc query had error '{response_dict['reason']}'"
                )
            return response_dict
        except Exception:
            raise CblEdgeServerBadResponseError(
                500, f"Get replication status from edge server had error '{response}'"
            )

    async def all_replication_status(self):
        curl = await self.edge_server.all_replication_status(curl=True)
        response = await self.remote_shell.run_command(curl)
        print(curl, response)
        try:
            response_dict = json.loads(response)
            if "error" in response_dict:
                raise CblEdgeServerBadResponseError(
                    500, f" Get replication status had error '{response_dict['error']}'"
                )
            return response_dict
        except Exception:
            raise CblEdgeServerBadResponseError(
                500,
                f"Get all replication statuses from edge server had error '{response}'",
            )

    async def stop_replication(self, replicator_id: str):
        curl_command = await self.edge_server.stop_replication(replicator_id, curl=True)
        response = await self.remote_shell.run_command(curl_command)
        try:
            response_dict = json.loads(response)
            if "error" in response_dict:
                raise CblEdgeServerBadResponseError(
                    500, f"Stop replication had error '{response_dict['reason']}'"
                )
            return response_dict
        except Exception:
            raise CblEdgeServerBadResponseError(
                500, f"Stop replication had error '{response}'"
            )

    async def changes_feed(
        self,
        db_name: str,
        scope: str = "",
        collection: str = "",
        since: Optional[int] = 0,
        feed: Optional[str] = "normal",
        limit: Optional[int] = None,
        filter_type: Optional[str] = None,
        doc_ids: Optional[List[str]] = None,
        include_docs: Optional[bool] = False,
        active_only: Optional[bool] = False,
        descending: Optional[bool] = False,
        heartbeat: Optional[int] = None,
        timeout: Optional[int] = None,
    ):
        curl_command = await self.edge_server.changes_feed(
            db_name,
            scope,
            collection,
            since,
            feed,
            limit,
            filter_type,
            doc_ids,
            include_docs,
            active_only,
            descending,
            heartbeat,
            timeout,
            curl=True,
        )
        response = await self.remote_shell.run_command(curl_command)
        try:
            response_dict = json.loads(response)
            if "error" in response_dict:
                raise CblEdgeServerBadResponseError(
                    500, f"Changes feed had error '{response_dict['reason']}'"
                )
            return response_dict
        except Exception:
            raise CblEdgeServerBadResponseError(
                500, f"Changes feed had error '{response}'"
            )

    async def named_query(
        self,
        db_name: str,
        scope: str = "",
        collection: str = "",
        name: Optional[str] = None,
        params: Optional[Dict] = None,
    ):
        curl_command = await self.edge_server.named_query(
            db_name, scope, collection, name, params, curl=True
        )
        print(f"Named query: {curl_command}")
        response = await self.remote_shell.run_command(curl_command)
        try:
            response_dict = json.loads(response)
            if "error" in response_dict:
                raise CblEdgeServerBadResponseError(
                    500, f"Named query had error '{response_dict}'"
                )
            return response_dict
        except Exception:
            raise CblEdgeServerBadResponseError(
                500, f"Named query had error '{response}'"
            )

    async def adhoc_query(
        self,
        db_name: str,
        scope: str = "",
        collection: str = "",
        query: Optional[str] = None,
        params: Optional[Dict] = None,
    ):
        curl_command = await self.edge_server.adhoc_query(
            db_name, scope, collection, query, params, curl=True
        )
        print(f"adhoc query: {curl_command}")
        response = await self.remote_shell.run_command(curl_command)
        try:
            response_dict = json.loads(response)
            if "error" in response_dict:
                raise CblEdgeServerBadResponseError(
                    500, f"Adhoc query had error '{response_dict}'"
                )
            return response_dict
        except Exception:
            raise CblEdgeServerBadResponseError(
                500, f"Adhoc query had error '{response}'"
            )

    async def add_document_auto_id(
        self, document: dict, db_name: str, scope: str = "", collection: str = "", expires:int=0,ttl:int=0
    ):
        curl_command = await self.edge_server.add_document_auto_id(
            document, db_name, scope, collection, curl=True, expires=expires, ttl=ttl
        )
        response = await self.remote_shell.run_command(curl_command)
        print(curl_command, response)
        try:
            response_dict = json.loads(response)
            if "error" in response_dict:
                raise CblEdgeServerBadResponseError(
                    500,
                    f"Add document with auto ID had error '{response_dict['reason']}'",
                )
            return response_dict
        except Exception:
            raise CblEdgeServerBadResponseError(
                500, f"Add document with auto ID had error '{response}'"
            )

    async def put_document_with_id(
        self,
        document: dict,
        doc_id: str,
        db_name: str,
        scope: str = "",
        collection: str = "",
        rev: Optional[str] = None,
        expires: int = 0,
        ttl: int = 0
    ) -> dict:
        curl_command = await self.edge_server.put_document_with_id(
            document, doc_id, db_name, scope, collection, curl=True, rev=rev, ttl=ttl, expires=expires
        )

        response = await self.remote_shell.run_command(curl_command)
        try:
            response_dict = json.loads(response)
            if "error" in response_dict:
                raise CblEdgeServerBadResponseError(
                    500, f"Add document with ID had error '{response_dict['reason']}'"
                )
            return response_dict
        except Exception:
            raise CblEdgeServerBadResponseError(
                500, f"Add document with ID had error '{response}'"
            )

    async def delete_sub_document(
        self,
        doc_id: str,
        revid: str,
        key: str,
        db_name: str,
        scope: str = "",
        collection: str = "",
    ) -> dict:
        curl_command = await self.edge_server.delete_sub_document(
            doc_id, revid, key, db_name, scope, collection, curl=True
        )

        response = await self.remote_shell.run_command(curl_command)
        try:
            response_dict = json.loads(response)
            if "error" in response_dict:
                raise CblEdgeServerBadResponseError(
                    500, f"Delete sub-document had error '{response_dict['reason']}'"
                )
            return response_dict
        except Exception:
            raise CblEdgeServerBadResponseError(
                500, f"Delete sub-document had error '{response}'"
            )

    async def put_sub_document(
        self,
        doc_id: str,
        revid: str,
        key: str,
        db_name: str,
        scope: str = "",
        collection: str = "",
        value=None,
    ) -> dict:
        curl_command = await self.edge_server.put_sub_document(
            doc_id, revid, key, db_name, scope, collection, value, curl=True
        )

        response = await self.remote_shell.run_command(curl_command)
        try:
            response_dict = json.loads(response)
            if "error" in response_dict:
                raise CblEdgeServerBadResponseError(
                    500, f"Put sub-document had error '{response_dict['reason']}'"
                )
            return response_dict
        except Exception:
            raise CblEdgeServerBadResponseError(
                500, f"Put sub-document had error '{response}'"
            )

    async def get_sub_document(
        self, doc_id: str, key: str, db_name: str, scope: str = "", collection: str = ""
    ):
        curl_command = await self.edge_server.get_sub_document(
            doc_id, key, db_name, scope, collection, curl=True
        )

        response = await self.remote_shell.run_command(curl_command)
        try:
            response_dict = json.loads(response)
            if "error" in response_dict:
                raise CblEdgeServerBadResponseError(
                    500, f"Get sub-document had error '{response_dict['reason']}'"
                )
            return response_dict
        except Exception:
            raise CblEdgeServerBadResponseError(
                500, f"Get sub-document had error '{response}'"
            )

    async def bulk_doc_op(
        self,
        docs: List[BulkDocOperation],
        db_name: str,
        scope: str = "",
        collection: str = "",
        new_edits: bool = True,
    ):
        curl_command = await self.edge_server.bulk_doc_op(
            docs, db_name, scope, collection, new_edits, curl=True
        )
        print(curl_command)
        response = await self.remote_shell.run_command(curl_command)
        try:
            response_dict = json.loads(response)
            if "error" in response_dict:
                raise CblEdgeServerBadResponseError(
                    500,
                    f"Bulk documents operation had error '{response_dict['reason']}'",
                )
            return response_dict
        except Exception:
            raise CblEdgeServerBadResponseError(
                500, f"Bulk documents operation had error '{response}'"
            )

    async def blip_sync(self, db_name: str, scope: str = "", collection: str = ""):
        curl_command = await self.edge_server.blip_sync(
            db_name, scope, collection, curl=True
        )

        response = await self.remote_shell.run_command(curl_command)
        try:
            response_dict = json.loads(response)
            if "error" in response_dict:
                raise CblEdgeServerBadResponseError(
                    500, f"BLIP sync had error '{response_dict['reason']}'"
                )
            return response_dict
        except Exception:
            raise CblEdgeServerBadResponseError(
                500, f"BLIP sync had error '{response}'"
            )

    async def disconnect(self):
        self.remote_shell.close()

    async def create_certificate(self):
        try:
            command = "openssl genrsa -out /opt/clientkey 2048"
            print(await self.remote_shell.run_command(command))
            command = f'openssl req -new -key /opt/clientkey -out /opt/client.csr -subj "/CN={self.edge_server}"'
            await self.remote_shell.run_command(command)
            command = f"sshpass -p couchbase scp -o StrictHostKeyChecking=no root@{self.edge_server.hostname}:/opt/couchbase-edge-server/cert/rootkey /opt"
            await self.remote_shell.run_command(command)
            command = f"sshpass -p couchbase scp -o StrictHostKeyChecking=no root@{self.edge_server.hostname}:/opt/couchbase-edge-server/cert/rootcert /opt"
            await self.remote_shell.run_command(command)
            time.sleep(60)
            command = "openssl x509 -req -in /opt/client.csr -CA /opt/rootcert -CAkey /opt/rootkey -CAcreateserial -out /opt/clientcert -days 365"
            await self.remote_shell.run_command(command)
            command = f"sshpass -p couchbase scp /opt/clientcert root@{self.edge_server.hostname}:/opt/couchbase-edge-server/cert  "
            await self.remote_shell.run_command(command)
            command = f"sshpass -p couchbase scp /opt/clientkey root@{self.edge_server.hostname}:/opt/couchbase-edge-server/cert "
            await self.remote_shell.run_command(command)
        except Exception as e:
            raise CblEdgeServerBadResponseError(500, str(e))

    async def get_tls_certificate(self):
        try:
            cmd_check_sshpass = "command -v sshpass || sudo apt-get update && sudo apt-get install -y sshpass"
            await self.remote_shell.run_command(cmd_check_sshpass)
            command = f"sshpass -p couchbase scp -o StrictHostKeyChecking=no root@{self.edge_server.hostname}:/opt/couchbase-edge-server/cert/certfile_tls /opt"
            print(command)
            await self.remote_shell.run_command(command)
        except Exception as e:
            raise CblEdgeServerBadResponseError(500, str(e))


class ClientFactory:
    def __init__(
        self,
        vms: list,
        edge_server: EdgeServer,
        num_clients_per_vm: int = 5,
        user="root",
        password="couchbase",
    ):
        self.vms = vms
        self.edge_server = edge_server
        self.num_clients_per_vm = num_clients_per_vm
        self.user = user
        self.password = password
        self.client_counter = 1
        self.clients: dict[str, HTTPClient] = {}  # client_id -> HTTPClient
        self.lock = (
            asyncio.Lock()
        )  # Lock to manage client creation and respawning concurrently

    async def create_clients(self):
        try:
            tasks = []
            for vm in self.vms:
                for _ in range(self.num_clients_per_vm):
                    tasks.append(self.create_client_for_vm(vm))
            await asyncio.gather(*tasks)
        except Exception as e:
            print(e)

    async def create_client_for_vm(self, vm):
        """
        Creates a client for a specific VM.
        """
        try:
            async with self.lock:
                client_id = self.client_counter
                self.client_counter += 1
                client = HTTPClient(
                    vm_ip=vm,
                    edge_server=self.edge_server,
                    client_id=client_id,
                    user=self.user,
                    password=self.password,
                )
                await client.connect()
                self.clients[client_id] = client
        except Exception as e:
            print(e)

    async def make_request(
        self, client: Optional[HTTPClient], method: str, *args, **kwargs
    ):
        if client is None:
            raise ValueError("Client is None")
        try:
            if hasattr(client, method):
                method_to_call = getattr(client, method)
            else:
                raise ValueError(f"The method does not exist: {method}")
            if not callable(method_to_call):
                raise ValueError(f"The attribute '{method}' is not callable.")
            # Call the method with provided arguments
            response = await method_to_call(*args, **kwargs)
            return response
        except Exception as e:
            print(f"Client {client.client_id} failed: {str(e)}")
            raise

    async def make_all_client_request(self, method: str, *args, **kwargs):
        tasks = [
            self.make_request(client, method, *args, **kwargs)
            for client in self.clients.values()
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        error = {}
        responses = {}
        failed = []
        for client_id, result in zip(self.clients.keys(), results):
            if isinstance(result, Exception):
                error[client_id] = str(result)
                failed.append(client_id)
            else:
                responses[client_id] = result
        return responses, error, failed

    # takes in a dict of type REST API: [client_id]
    # eg: method={"get_all_documents":[1,3,
    # 5]} etc
    # response: method: {1:resp,3:resp}
    async def make_unique_client_request(self, methods: dict, *args, **kwargs):
        responses = {}
        error = {}
        failed = []
        for method, idx in methods.items():
            tasks = [
                self.make_request(self.clients.get(id), method, args, kwargs)
                for id in idx
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            response = {}
            for client_id, result in zip(idx, results):
                if isinstance(result, Exception):
                    error[client_id] = str(result)
                    failed.append(client_id)
                else:
                    response[client_id] = result
            responses[method] = response
        return responses, error, failed

    # {client_id:{method:"",params:{key:value}}}
    async def make_unique_params_client_request(self, methods: dict):
        error = {}
        failed = []
        tasks = [
            self.make_request(
                self.clients.get(idx),
                method_dict.get("method"),
                **method_dict.get("params"),
            )
            for idx, method_dict in methods.items()
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        response = {}
        for client_id, result in zip(methods.keys(), results):
            if isinstance(result, Exception):
                error[client_id] = str(result)
                failed.append(client_id)
            else:
                response[client_id] = result
        return response, error, failed

    async def disconnect(self):
        """Closes all SSH connections."""
        tasks = [client.disconnect() for client in self.clients.values()]
        await asyncio.gather(*tasks)
