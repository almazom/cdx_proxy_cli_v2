from __future__ import annotations

from cdx_proxy_cli_v2.proxy.runtime import ProxyRuntime as RuntimeProxyRuntime
from cdx_proxy_cli_v2.proxy.server import ProxyRuntime as ServerProxyRuntime


def test_runtime_module_reexports_server_proxy_runtime() -> None:
    assert RuntimeProxyRuntime is ServerProxyRuntime
