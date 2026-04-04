from __future__ import annotations


def main() -> int:
    from cdx_proxy_cli_v2.cli.main import main as _main

    return _main()

__all__ = ["main"]
