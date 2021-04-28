from __future__ import absolute_import
from __future__ import print_function

from past.builtins import intern
from builtins import range
import optparse
import sys
import types

import clr
from clr.commands import get_command_spec, resolve_command
from clr.options import add_global_options, handle_global_options
from functools import reduce

def apply(fn, args, kwargs):
    fn(*args, **kwargs)

def main():
    argv = sys.argv
    parser = optparse.OptionParser(add_help_option=False)
    add_global_options(parser)
    ghelp = parser.format_option_help()

    # Find the first arg that does not start with a '-'. This is the
    # command.
    try:
        query = argv[1]
    except IndexError:
        query = 'system:help'

    _, cmd, namespace_key, cmd_name = resolve_command(query)

    # Parse the command line arguments.
    spec, vararg = get_command_spec(cmd)

    # Construct an option parser for the chosen command by inspecting
    # its arguments.
    for a, defval in spec:
        type2str = {
            int: 'int',
            int: 'long',
            float: 'float',
            bytes: 'string',
            str: 'string',
            complex: 'complex',
        }

        o = optparse.Option('--%s' % a)

        if defval is intern('default'):
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

        if defval is not intern('default'):
            o.default = defval

        o.dest = '_cmd_%s' % a

        parser.add_option(o)

    opts, args = parser.parse_args(argv[2:])

    hooks = handle_global_options(opts)

    # The first argument is the command.
    kwargs = [k_v for k_v in list(opts.__dict__.items()) if k_v[0].startswith('_cmd_')]
    kwargs = dict([(k[5:], v) for k, v in kwargs])

    # Positional args override corresponding kwargs
    for i in range(min(len(args), len(spec))):
        del kwargs[spec[i][0]]

    # Now make sure that all nondefault arguments are specified.
    defargs = [a_s for a_s in spec if a_s[1] is intern('default')]
    if len(args) < len(defargs):
        print('Not all non-default arguments were specified!', file=sys.stderr)
        sys.exit(1)

    # Special case: print global option help.
    if namespace_key == 'system' and cmd_name == 'help':
        print(ghelp)

    # Compose the run hooks.
    run = reduce(
        lambda c, fun: (lambda *a, **kw: fun(c, a, kw)),
        hooks.get('run', [apply])
    )

    run(cmd, args, kwargs)
