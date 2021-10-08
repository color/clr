import sys
import os
import getpass
import beeline
import socket
import traceback
from contextlib import contextmanager
from clr.commands import resolve_command, get_namespace
from clrenv import env


@contextmanager
def init_beeline(namespace_key, cmd_name):
    # clrenv < 0.2.0 has a bug in the `in` operator at the root level.
    if env.get("honeycomb") is None:
        return

    try:
        beeline.init(
            writekey=env.honeycomb.writekey,
            dataset="clr",
            service_name="clr",
            debug=False,
        )
    except Exception as e:
        # Honeycomb logging is completely optional and all later calls to
        # beeline are silently no-ops if not initialized. Simply log the
        # failure and continue normally.
        print("Failed to initialize beeline: %s", e, file=sys.stderr)

    with beeline.tracer("cmd"):
        beeline.add_context_field("namespace", namespace_key)
        beeline.add_context_field("cmd", cmd_name)
        beeline.add_context_field("username", getpass.getuser())
        beeline.add_context_field("hostname", socket.gethostname())

        # Bounce back to the calling code.
        yield

    beeline.close()


def main(argv=None):
    if not argv:
        argv = sys.argv
    query = "system:help"
    if len(argv) > 1:
        query = argv[1]

    namespace_key, cmd_name = resolve_command(query)
    namespace = get_namespace(namespace_key)

    # Default successful exit code.
    exit_code = 0

    with init_beeline(namespace_key, cmd_name):
        with beeline.tracer("parse_args"):
            bound_args = namespace.parse_args(cmd_name, argv[2:])

        # Some namespaces define a cmdinit function which should be run first.
        if hasattr(namespace.instance, "cmdinit"):
            with beeline.tracer("cmdinit"):
                namespace.instance.cmdinit()

        with beeline.tracer("cmdrun"):
            result = None
            try:
                result = namespace.command_callables[cmd_name](
                    *bound_args.args, **bound_args.kwargs
                )
                if isinstance(result, (int, bool)):
                    exit_code = int(result)
            except:
                print(traceback.format_exc(), file=sys.stderr)
                beeline.add_context_field("raised_exception", True)
                exit_code = 999

        beeline.add_context_field("exit_code", exit_code)

    sys.exit(exit_code)
