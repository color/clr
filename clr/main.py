from __future__ import absolute_import

import optparse
import sys
import types

import clr
from clr.commands import get_command_spec, resolve_command
from clr.options import add_global_options, handle_global_options


def main():
    argv = sys.argv
    parser = optparse.OptionParser(add_help_option=False)
    add_global_options(parser)
    ghelp = parser.format_option_help()

    # Find the first arg that does not start with a '-'. This is the
    # command.
    try:
        cmd_ = argv[1]
    except IndexError:
        cmd_ = 'system:help'

    _, cmd, ns_, cmd_ = resolve_command(cmd_)

    # Parse the command line arguments.
    spec, vararg = get_command_spec(cmd)

    # Construct an option parser for the chosen command by inspecting
    # its arguments.
    for a, defval in spec:
        type2str = {
            types.IntType: 'int',
            types.LongType: 'long',
            types.FloatType: 'float',
            types.StringType: 'string',
            types.UnicodeType: 'string',
            types.ComplexType: 'complex',
        }

        o = optparse.Option('--%s' % a)

        if defval is intern('default'):
            pass
        elif isinstance(defval, types.BooleanType):
            if defval:
                o = optparse.Option('--no%s' % a)
                o.action = 'store_false'
            else:
                o.action = 'store_true'

            o.type = None               # Huh.
        elif isinstance(defval, tuple(type2str.keys())):
            o.action = 'store'
            t = map(lambda x: x[1],
                    filter(lambda (t, s): isinstance(defval, t),
                           type2str.iteritems()))
            assert len(t) == 1

            o.type = t[0]

        if defval is not intern('default'):
            o.default = defval

        o.dest = '_cmd_%s' % a

        parser.add_option(o)

    opts, args = parser.parse_args(argv[2:])

    hooks = handle_global_options(opts)

    # The first argument is the command.
    kwargs = filter(lambda (k, v): k.startswith('_cmd_'), opts.__dict__.items())
    kwargs = dict([(k[5:], v) for k, v in kwargs])

    # Positional args override corresponding kwargs
    for i in xrange(min(len(args), len(spec))):
        del kwargs[spec[i][0]]

    # Now make sure that all nondefault arguments are specified.
    defargs = filter(lambda (a, s): s is intern('default'), spec)
    if len(args) < len(defargs):
        print >>sys.stderr, 'Not all non-default arguments were specified!'
        sys.exit(1)

    # Special case: print global option help.
    if ns_ == 'system' and cmd_ == 'help':
        print ghelp

    # Compose the run hooks.
    run = reduce(
        lambda c, fun: (lambda *a, **kw: fun(c, a, kw)),
        hooks.get('run', [apply])
    )

    run(cmd, args, kwargs)
