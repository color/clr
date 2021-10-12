import sys
import os
import getpass
import socket
import traceback
from contextlib import contextmanager
from clr.commands import resolve_command, get_namespace

DEBUG_MODE = os.environ.get("CLR_DEBUG", "").lower() in ("true", "1")

# In general using a try to handle if we should import or not is not best
# practice. However in this case we do not want this code to possibly
# break anything so we use try to figure out if we should import or not.
beeline = None
try:
    import beeline
except:
    if DEBUG_MODE:
        import traceback

        print("Failed to import beeline.", file=sys.stderr)
        traceback.print_exc()

@contextmanager
def init_beeline(namespace_key, cmd_name):
    if beeline is None:
        yield
        return

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
            import traceback

            print("Failed to initialize beeline.", file=sys.stderr)
            traceback.print_exc()


    with beeline.tracer("cmd"):
        beeline.add_trace_field("namespace", namespace_key)
        beeline.add_trace_field("cmd", cmd_name)
        beeline.add_trace_field("username", getpass.getuser())
        beeline.add_trace_field("hostname", socket.gethostname())

        # Bounce back to the calling code.
        yield

    beeline.close()

@contextmanager
def beeline_tracer(name):
    if beeline is None:
        yield
        return

    with beeline.tracer(name):
        yield

def beeline_add_trace_field(key, value):
    if beeline is None:
        return

    beeline.add_trace_field(key, value)

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
        with beeline_tracer("parse_args"):
            bound_args = namespace.parse_args(cmd_name, argv[2:])

        # Some namespaces define a cmdinit function which should be run first.
        if hasattr(namespace.instance, "cmdinit"):
            with beeline.tracer("cmdinit"):
                namespace.instance.cmdinit()

        with beeline_tracer("cmdrun"):
            result = None
            try:
                result = namespace.command_callables[cmd_name](
                    *bound_args.args, **bound_args.kwargs
                )
                if isinstance(result, (int, bool)):
                    exit_code = int(result)
            except:
                print(traceback.format_exc(), file=sys.stderr)
                beeline_add_trace_field("raised_exception", True)
                exit_code = 999

        beeline_add_trace_field("exit_code", exit_code)

    sys.exit(exit_code)
