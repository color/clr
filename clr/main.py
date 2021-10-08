import sys
import os
import getpass
import beeline
import socket
from clr.commands import resolve_command, get_namespace
from clrenv import env

def init_beeline(service_name):
    if 'honeycomb' in env:
        try:
            beeline.init(
                writekey=env.honeycomb.writekey,
                dataset='clr',
                service_name=service_name,
                debug=False,
            )
        except Exception as e:
            print('Failed to initialize beeline: %s', e, file=sys.stderr)

def main(argv=None):
    if not argv:
        argv = sys.argv
    query = "system:help"
    if len(argv) > 1:
        query = argv[1]

    namespace_key, cmd_name = resolve_command(query)
    namespace = get_namespace(namespace_key)
    bound_args = namespace.parse_args(cmd_name, argv[2:])

    init_beeline(namespace_key)
    trace = beeline.start_trace(context={
        "name": cmd_name,
        "username": getpass.getuser(),
        "hostname": socket.gethostname(),
    })

    if hasattr(namespace.instance, "cmdinit"):
        cmdinit_span = beeline.start_span({"name": "cmdinit"})
        namespace.instance.cmdinit()
        beeline.finish_span(cmdinit_span)

    cmdrun_span = beeline.start_span({"name": "cmdrun"})
    exit_code = 0
    result = None
    try:
        result = namespace.command_callables[cmd_name](
            *bound_args.args, **bound_args.kwargs
        )
    except Exception as e:
        print('Error running command: %s', e, file=sys.stderr)
        beeline.add_context_field('raised_exception', True)
        exit_code = 1

    beeline.finish_span(cmdrun_span)

    # Support exit codes. This supports int and bool return values.
    if result is not None and isinstance(result, (int, bool)):
        exit_code = result

    beeline.add_context_field('exit_code', exit_code)
    beeline.finish_trace(trace)
    beeline.close()

    # only exit if we have a non-zero code otherwise we want python to handle
    # exit codes
    if exit_code != 0:
        sys.exit(exit_code)
