"""cdx CLI commands package."""

from cdx_proxy_cli_v2.cli.commands.all import handle_all
from cdx_proxy_cli_v2.cli.commands.doctor import handle_doctor
from cdx_proxy_cli_v2.cli.commands.limits import handle_limits
from cdx_proxy_cli_v2.cli.commands.logs import handle_logs
from cdx_proxy_cli_v2.cli.commands.migrate import handle_migrate
from cdx_proxy_cli_v2.cli.commands.proxy import handle_proxy
from cdx_proxy_cli_v2.cli.commands.reset import handle_reset
from cdx_proxy_cli_v2.cli.commands.rotate import handle_rotate
from cdx_proxy_cli_v2.cli.commands.run_server import handle_run_server
from cdx_proxy_cli_v2.cli.commands.status import handle_status
from cdx_proxy_cli_v2.cli.commands.stop import handle_stop
from cdx_proxy_cli_v2.cli.commands.trace import handle_trace

__all__ = [
    "handle_all",
    "handle_doctor",
    "handle_limits",
    "handle_logs",
    "handle_migrate",
    "handle_proxy",
    "handle_reset",
    "handle_rotate",
    "handle_run_server",
    "handle_status",
    "handle_stop",
    "handle_trace",
]
