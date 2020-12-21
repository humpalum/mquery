import json
import time
import zmq  # type: ignore
from typing import Dict, Any, List, Optional


Json = Dict[str, Any]


class PopResult:
    def __init__(
        self,
        was_locked: bool,
        files: List[str],
        iterator_pos: int,
        total_files: int,
    ) -> None:
        self.was_locked = was_locked
        self.files = files
        self.iterator_pos = iterator_pos
        self.total_files = total_files

    @property
    def iterator_empty(self) -> bool:
        """ Is it safe to remove the iterator after this operation? """
        if self.was_locked:
            return False
        return self.iterator_pos >= self.total_files


class UrsaDb:
    def __init__(self, backend: str) -> None:
        self.backend = backend

    def make_socket(self, recv_timeout: int = 2000) -> zmq.Context:
        context = zmq.Context()
        socket = context.socket(zmq.REQ)
        socket.setsockopt(zmq.LINGER, 0)
        socket.setsockopt(zmq.RCVTIMEO, recv_timeout)
        socket.connect(self.backend)
        return socket

    def query(
        self,
        query: str,
        taints: List[str] = [],
        dataset: Optional[str] = None,
    ) -> Json:
        socket = self.make_socket(recv_timeout=-1)

        start = time.perf_counter()
        command = "select "
        if taints:
            taints_str = '", "'.join(taints)
            taints_whole_str = '["' + taints_str + '"]'
            command += f"with taints {taints_whole_str} "
        if dataset:
            command += f'with datasets ["{dataset}"] '

        command += f"into iterator {query};"
        socket.send_string(command)

        response = socket.recv_string()
        socket.close()
        end = time.perf_counter()

        res = json.loads(response)

        if "error" in res:
            return {
                "error": "ursadb failed: "
                + res.get("error", {}).get("message", "(no message)")
            }

        iterator = res["result"]["iterator"]
        file_count = res["result"]["file_count"]

        return {
            "time": (end - start),
            "iterator": iterator,
            "file_count": file_count,
        }

    def pop(self, iterator: str, count: int) -> PopResult:
        socket = self.make_socket(recv_timeout=-1)

        query = f'iterator "{iterator}" pop {count};'
        socket.send_string(query)

        response = socket.recv_string()
        socket.close()

        res = json.loads(response)
        if "error" in res:
            if res["error"].get("retry", False):
                # iterator locked, try again in a sec
                return PopResult(True, [], 0, 0)
            # return empty file set - this will clear the job from the db!
            return PopResult(False, [], 0, 0)

        res = res["result"]
        iterator_pos = res["iterator_position"]
        total_files = res["total_files"]

        return PopResult(False, res["files"], iterator_pos, total_files)

    def status(self) -> Json:
        socket = self.make_socket()
        socket.send_string("status;")
        response = socket.recv_string()
        socket.close()

        return json.loads(response)

    def topology(self) -> Json:
        socket = self.make_socket()
        socket.send_string("topology;")
        response = socket.recv_string()
        socket.close()

        return json.loads(response)

    def execute_command(self, command: str) -> Json:
        socket = self.make_socket(recv_timeout=-1)
        socket.send_string(command)
        response = socket.recv_string()
        socket.close()

        return json.loads(response)

    def close(self) -> None:
        pass
