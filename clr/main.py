import sys
import os
import getpass
import beeline
import platform
import traceback
import signal
from contextlib import contextmanager
from clr.commands import resolve_command, get_namespace

DEBUG_MODE = os.environ.get("CLR_DEBUG", "").lower() in ("true", "1")


def on_exit(signum, frame):
    beeline.add_trace_field("killed_by_signal", signal.Signals(signum).name)
    beeline.close()


def wrap_signal_handler(sig):
    old_handler = signal.getsignal(sig)

    def new_handler(signum, frame):
        on_exit(signum, frame)
        old_handler(signum, frame)

    signal.signal(sig, new_handler)


wrap_signal_handler(signal.SIGINT)
wrap_signal_handler(signal.SIGTERM)


@contextmanager
def init_beeline(namespace_key, cmd_name):
    try:
        from clrenv import env

        # clrenv < 0.2.0 has a bug in the `in` operator at the root level.
        if env.get("honeycomb") is not None:
            beeline.init(
                writekey=env.honeycomb.writekey,
                dataset="clr",
                service_name="clr",
                debug=False,
            )
    except:
        # Honeycomb logging is completely optional and all later calls to
        # beeline are silently no-ops if not initialized. Simply log the
        # failure and continue normally. This includes if clrenv can not be
        # loaded.
        if DEBUG_MODE:
            print("Failed to initialize beeline.", file=sys.stderr)
            traceback.print_exc()

    with beeline.tracer("cmd"):
        beeline.add_trace_field("namespace", namespace_key)
        beeline.add_trace_field("cmd", cmd_name)
        beeline.add_trace_field("username", getpass.getuser())
        beeline.add_trace_field("hostname", platform.node())

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
                beeline.add_trace_field("raised_exception", True)
                exit_code = 999

        beeline.add_trace_field("exit_code", exit_code)

    sys.exit(exit_code)
