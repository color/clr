import sys
from clr.commands import resolve_command, get_namespace

def main():
    query = 'system:help'
    if len(sys.argv) > 1:
        query = sys.argv[1]

    namespace_key, cmd_name = resolve_command(query)
    namespace = get_namespace(namespace_key)
    bound_args = namespace.parse_args(cmd_name, sys.argv[2:])

    # Call the command.
    namespace.command_callables[cmd_name](*bound_args.args, **bound_args.kwargs)
