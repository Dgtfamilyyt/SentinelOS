"""
tools/network/http_get.py
=========================
HttpGet — perform an HTTP GET request and return response details.
"""

import urllib.request
import urllib.error
import ssl
import json as _json

from tools.base import Tool
from tools.policy import PermissionClass


class HttpGet(Tool):
    """
    Perform an HTTP GET request.

    Parameters:
        url     (str):  Target URL
        timeout (int):  Timeout in seconds (default: 10)
        headers (dict): Optional additional headers
    """

    name        = "http_get"
    description = "Perform an HTTP GET request and return status, headers, and body."
    category    = "network"
    permission  = PermissionClass.READ_ONLY

    parameters  = {
        "url": {
            "type":     "string",
            "required": True,
            "description": "Target URL including protocol (http:// or https://)",
        },
        "timeout": {
            "type":     "integer",
            "required": False,
            "description": "Request timeout in seconds (default: 10)",
        },
    }

    def execute(self, url: str, timeout: int = 10) -> dict:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode    = ssl.CERT_NONE

        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "Sentinel-Agent/1.0"},
            )
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
                body = resp.read(65536).decode("utf-8", errors="replace")
                return {
                    "url":         url,
                    "status_code": resp.status,
                    "headers":     dict(resp.headers),
                    "body":        body[:4096],
                    "body_length": len(body),
                    "success":     True,
                }
        except urllib.error.HTTPError as exc:
            return {
                "url":         url,
                "status_code": exc.code,
                "headers":     {},
                "body":        str(exc.reason),
                "success":     False,
                "error":       str(exc),
            }
        except Exception as exc:
            return {
                "url":     url,
                "success": False,
                "error":   str(exc),
            }
