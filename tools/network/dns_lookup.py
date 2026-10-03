"""
tools/network/dns_lookup.py
===========================
DnsLookup — resolve a hostname to IP addresses.
"""

import socket

from tools.base import Tool
from tools.policy import PermissionClass


class DnsLookup(Tool):
    """
    Resolve a hostname to its IP addresses.

    Parameters:
        hostname (str): The hostname to resolve
    """

    name        = "dns_lookup"
    description = "Resolve a hostname to IP addresses via DNS."
    category    = "network"
    permission  = PermissionClass.READ_ONLY

    parameters  = {
        "hostname": {
            "type":     "string",
            "required": True,
            "description": "Hostname to resolve",
        },
    }

    def execute(self, hostname: str) -> dict:
        try:
            infos = socket.getaddrinfo(hostname, None)
            addresses = list({info[4][0] for info in infos})
            return {
                "hostname":  hostname,
                "addresses": addresses,
                "resolved":  True,
            }
        except socket.gaierror as exc:
            return {
                "hostname":  hostname,
                "addresses": [],
                "resolved":  False,
                "error":     str(exc),
            }
