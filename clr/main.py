import sys
import os
import getpass
import beeline
import time
import traceback
import atexit
from contextlib import contextmanager
from .commands import resolve_command, get_namespace
from ._version import __version__

DEBUG_MODE = os.environ.get("CLR_DEBUG", "").lower() in ("true", "1")

# Store data to send to honeycomb as a global so it can be accessed from an
# atexit method. None of this code should ever be called from within a long
# running process.
honeycomb_data = {}


def send_to_honeycomb():
    """Attempts to log usage data to honeycomb.

    Honeycomb logging is completely optional. If there are any failures
    simply continue as normal. This includes if clrenv can not be loaded.

    These metrics are sent to honeycomb as an event rather than a trace for two
    reasons:
    1) They don't really fit the web requests model.
    2) Downstream code might have its own tracing which we don't want to interfere
    with.
    """
    try:
        from clrenv import env

        # clrenv < 0.2.0 has a bug in the `in` operator at the root level.
        if env.get("honeycomb") is None:
            return

        beeline.init(
            writekey=env.honeycomb.writekey,
            dataset="clr",
            service_name="clr",
        )

        # Convert start_time into a duration.
        honeycomb_data["duration_ms"] = int(
            1000 * (time.time() - honeycomb_data["start_time"])
        )
        del honeycomb_data["start_time"]

        honeycomb_data["username"] = getpass.getuser()
        honeycomb_data["clr_version"] = __version__
        honeycomb_data["color_key_mode"] = env.key_mode

        beeline.send_now(honeycomb_data)
        beeline.close()
    except:
        if DEBUG_MODE:
            print("Failed to initialize beeline.", file=sys.stderr)
            print(traceback.format_exc(), file=sys.stderr)


# Will get run on normal completion, exceptions and sys.exit.
atexit.register(send_to_honeycomb)


def main(argv=None):
    if not argv:
        argv = sys.argv
    query = "system:help"
    if len(argv) > 1:
        query = argv[1]

    start_time = time.time()
    namespace_key, cmd_name = resolve_command(query)

    honeycomb_data["start_time"] = start_time
    honeycomb_data["namespace_key"] = namespace_key
    honeycomb_data["cmd_name"] = cmd_name

    namespace = get_namespace(namespace_key)

    # Default successful exit code.
    exit_code = 0

    bound_args = namespace.parse_args(cmd_name, argv[2:])
    # TODO(michael.cusack): Args are currently not logged to honeycomb for PHI reasons.
    # Evaluate whether this is really an issue.
    # honeycomb_data['args'] = bound_args.arguments

    # Some namespaces define a cmdinit function which should be run first.
    if hasattr(namespace.instance, "cmdinit"):
        namespace.instance.cmdinit()

    result = None
    try:
        result = namespace.command_callables[cmd_name](
            *bound_args.args, **bound_args.kwargs
        )
        if isinstance(result, (int, bool)):
            exit_code = int(result)
    except BaseException as e:
        # BaseException so we still will see KeyboardInterrupts
        honeycomb_data["raised_exception"] = repr(e)
        raise

    honeycomb_data["exit_code"] = exit_code
    sys.exit(exit_code)
