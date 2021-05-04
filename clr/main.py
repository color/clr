import optparse
import sys
import types

from clr.commands import get_command_spec, resolve_command, get_namespace, NO_DEFAULT

def apply(fn, args, kwargs):
    fn(*args, **kwargs)

def main():
    argv = sys.argv
    parser = optparse.OptionParser(add_help_option=False)
    ghelp = parser.format_option_help()

    # Find the first arg that does not start with a '-'. This is the
    # command.
    try:
        query = argv[1]
    except IndexError:
        query = 'system:help'

    namespace_key, cmd_name = resolve_command(query)
    cmd = get_namespace(namespace_key).command_callables[cmd_name]

    # Parse the command line arguments.
    spec = get_command_spec(cmd)

    # Construct an option parser for the chosen command by inspecting
    # its arguments.
    for a, defval in spec.args:
        type2str = {
            int: 'int',
            int: 'long',
            float: 'float',
            bytes: 'string',
            str: 'string',
            complex: 'complex',
        }

        o = optparse.Option('--%s' % a)

        if defval == NO_DEFAULT:
            pass
        elif isinstance(defval, bool):
            if defval:
                o = optparse.Option('--no%s' % a)
                o.action = 'store_false'
            else:
                o.action = 'store_true'

            o.type = None               # Huh.
        elif isinstance(defval, tuple(type2str.keys())):
            o.action = 'store'
            t = [x[1] for x in [t_s for t_s in iter(type2str.items()) if isinstance(defval, t_s[0])]]
            assert len(t) == 1

            o.type = t[0]

        if defval != NO_DEFAULT:
            o.default = defval

        o.dest = '_cmd_%s' % a

        parser.add_option(o)

    opts, args = parser.parse_args(argv[2:])

    # The first argument is the command.
    kwargs = [k_v for k_v in list(opts.__dict__.items()) if k_v[0].startswith('_cmd_')]
    kwargs = dict([(k[5:], v) for k, v in kwargs])

    # Positional args override corresponding kwargs
    for i in range(min(len(args), len(spec.args))):
        del kwargs[spec.args[i][0]]

    # Now make sure that all nondefault arguments are specified.
    defargs = [a_s for a_s in spec.args if a_s[1] == NO_DEFAULT]
    if len(args) < len(defargs):
        print('Not all non-default arguments were specified!', file=sys.stderr)
        get_namespace('system').instance.print_help_for_command(namespace_key, cmd_name)
        sys.exit(1)

    # Special case: print global option help.
    if namespace_key == 'system' and cmd_name == 'help':
        print(ghelp)

    cmd(*args, **kwargs)
