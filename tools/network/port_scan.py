"""
tools/network/port_scan.py
==========================
PortScan — TCP port scanner using Python sockets (no nmap dependency).

Supports single ports and port ranges. Authorized-scope check is performed
by the agent's authorization model before calling this tool.
"""

import socket
from concurrent.futures import ThreadPoolExecutor, as_completed

from tools.base import Tool
from tools.policy import PermissionClass


class PortScan(Tool):
    """
    Scan TCP ports on a target host.

    Parameters:
        host    (str):  Target IP or hostname
        ports   (str):  Port specification: "80", "22,80,443", "1-1024"
        timeout (float): Per-port timeout in seconds (default: 1.0)
        threads (int):  Concurrent scan threads (default: 50)
    """

    name        = "port_scan"
    description = "Scan TCP ports on a target host and report open/closed status."
    category    = "network"
    permission  = PermissionClass.RESTRICTED  # Requires policy + auth scope

    parameters  = {
        "host": {
            "type":     "string",
            "required": True,
            "description": "Target hostname or IP address",
        },
        "ports": {
            "type":     "string",
            "required": False,
            "description": "Port spec: single '80', list '22,80,443', range '1-1024' (default: top 100)",
        },
        "timeout": {
            "type":     "number",
            "required": False,
            "description": "Per-port connection timeout in seconds (default: 1.0)",
        },
        "threads": {
            "type":     "integer",
            "required": False,
            "description": "Concurrent scan threads (default: 50, max: 200)",
        },
    }

    # Common ports scanned when no range specified
    TOP_PORTS = [
        21, 22, 23, 25, 53, 80, 110, 111, 135, 139, 143, 443, 445, 993, 995,
        1723, 3306, 3389, 5900, 8080, 8443, 8888,
    ]

    def execute(
        self,
        host:    str,
        ports:   str    = None,
        timeout: float  = 1.0,
        threads: int    = 50,
    ) -> dict:
        port_list = self._parse_ports(ports)
        threads   = min(threads, 200)
        open_ports  = []
        closed_ports = []

        def check_port(port: int) -> tuple[int, bool, str]:
            try:
                with socket.create_connection((host, port), timeout=timeout):
                    return port, True, ""
            except (ConnectionRefusedError, OSError):
                return port, False, ""
            except Exception as exc:
                return port, False, str(exc)

        with ThreadPoolExecutor(max_workers=threads) as pool:
            futures = {pool.submit(check_port, p): p for p in port_list}
            for future in as_completed(futures):
                port, is_open, error = future.result()
                if is_open:
                    open_ports.append(port)

        open_ports.sort()
        return {
            "host":        host,
            "ports_scanned": len(port_list),
            "open_ports":  open_ports,
            "open_count":  len(open_ports),
            "summary":     f"{len(open_ports)} open ports found on {host}",
        }

    def _parse_ports(self, spec: str | None) -> list[int]:
        if not spec:
            return self.TOP_PORTS

        ports = []
        for part in spec.split(","):
            part = part.strip()
            if "-" in part:
                try:
                    start, end = part.split("-", 1)
                    ports.extend(range(int(start), int(end) + 1))
                except ValueError:
                    pass
            else:
                try:
                    ports.append(int(part))
                except ValueError:
                    pass

        return [p for p in ports if 1 <= p <= 65535]
