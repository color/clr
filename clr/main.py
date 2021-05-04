import optparse
import sys
import types

from clr.commands import resolve_command, get_namespace

def apply(fn, args, kwargs):
    fn(*args, **kwargs)

def main():
    query = 'system:help'
    if len(sys.argv) > 1:
        query = sys.argv[1]

    namespace_key, cmd_name = resolve_command(query)
    namespace = get_namespace(namespace_key)
    cmd_signature = namespace.command_specs[cmd_name].signature

    # Parse the command line arguments, starting after command name.
    parsed = namespace.arguement_parser(cmd_name).parse_args(sys.argv[2:])
    print(parsed)
    # Turn parsed args namespace into callable bindable args.
    cmd_args = []
    cmd_kwargs = {}
    for param in cmd_signature.parameters.values():
        value = getattr(parsed, param.name)
        if param.kind in (param.POSITIONAL_ONLY, param.POSITIONAL_OR_KEYWORD):
            cmd_args.append(value)
        elif param.kind == param.VAR_POSITIONAL:
            cmd_args.extend(value)
        elif param.kind == param.KEYWORD_ONLY:
            cmd_kwargs[param.name] = value

    # Ensure the signature is valid. Could be skipped, but adds correctness and
    # gives a nice error message then something is wrong.
    bound = cmd_signature.bind(*cmd_args, **cmd_kwargs)
    bound.apply_defaults()

    # Call the command.
    namespace.command_callables[cmd_name](*bound.args, **bound.kwargs)
