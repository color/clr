import sys
from clr.commands import resolve_command, get_namespace


def main(argv=None):
    if not argv:
        argv = sys.argv
    query = "system:help"
    if len(argv) > 1:
        query = argv[1]

    namespace_key, cmd_name = resolve_command(query)
    namespace = get_namespace(namespace_key)
    bound_args = namespace.parse_args(cmd_name, argv[2:])

    # Call the command.
    if hasattr(namespace.instance, 'cmdinit'):
        namespace.instance.cmdinit()
    result = namespace.command_callables[cmd_name](
        *bound_args.args, **bound_args.kwargs
    )
    # Support exit codes.
    if type(result) == int:
        sys.exit(result)
