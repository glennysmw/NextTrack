"""Tests for the test suite's own network guard.

The README and the report both claim that no test makes a real network call. That
claim is only worth as much as the mechanism enforcing it, and the mechanism has
already been wrong once: the original socket-level guard did not catch async httpx on
Windows, where the Proactor event loop connects through overlapped I/O rather than
``socket.socket.connect``. The AcousticBrainz bulk client made live requests from the
suite for exactly that reason. These tests pin the guard so a future gap fails here
rather than quietly re-enabling live traffic.
"""
import socket

import httpx
import pytest


async def test_async_httpx_to_an_external_host_is_blocked():
    with pytest.raises(AssertionError, match="live network connection"):
        async with httpx.AsyncClient() as client:
            await client.get("https://acousticbrainz.org/api/v1/low-level")


def test_sync_httpx_to_an_external_host_is_blocked():
    with pytest.raises(AssertionError, match="live network connection"):
        httpx.get("https://musicbrainz.org/ws/2/recording")


def test_raw_socket_to_an_external_host_is_blocked():
    with pytest.raises(AssertionError, match="live network connection"):
        socket.create_connection(("musicbrainz.org", 443), timeout=5)


def test_loopback_is_still_permitted():
    """The guard must not break asyncio or pytest, which open local socket pairs."""
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    try:
        client = socket.create_connection(listener.getsockname(), timeout=5)
        client.close()
    finally:
        listener.close()


def test_the_app_under_test_is_still_reachable(client, mock_sources):
    """TestClient addresses the app as 'testserver'; that must stay allowed."""
    assert client.get("/api/v1/health").status_code == 200
