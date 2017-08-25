from __future__ import print_function
from past.builtins import execfile
from builtins import zip
from builtins import object
import inspect
import sys
import textwrap
import types

import clr.config
from clr.util import path_of_module


def print_help_for_cmd(cmd_, prefix=''):
    w = textwrap.TextWrapper(
        initial_indent=prefix, subsequent_indent=prefix,
        width=70)

    _, cmd, _, _ = resolve_command(cmd_)

    spec, vararg = get_command_spec(cmd)

    is_default = lambda a_s: a_s[1] is sys.intern('default')
    req = [spec_item for spec_item in spec if is_default(spec_item)]
    notreq = [spec_item for spec_item in spec if not is_default(spec_item)]

    args = []
    if len(req) > 0:
        args.append(' '.join(['<%s>' % a for a, _ in req]))

    if len(notreq) > 0:
        def atxt(a, v):
            if isinstance(v, bool):
                if v:
                    return '--no%s' % a
                else:
                    return '--%s' % a

            else:
                return '--%s=%s' % (a, v)

        args.append('[%s]' % ' '.join([atxt(a, v) for a, v in notreq]))

    if vararg is not None:
        args.append('[%s...]' % vararg)

    print(w.fill('%s %s' % (cmd_, ' '.join(args))))

    w.initial_indent += '  '
    w.subsequent_indent += '  '

    doc = inspect.getdoc(cmd)
    for l in doc.split('\n'):
        print(w.fill(l))

def get_commands():
    cmds = dict((ns, get_command(ns)) for ns in list(clr.config.commands().keys()))
    cmds['system'] = System()

    return cmds

def get_command(which):
    if which == 'system':
        obj = System()
    else:
        path = path_of_module(clr.config.commands()[which])
        d    = {}
        execfile(path, d)
        obj = d['COMMANDS']

    # Backfill namespace.
    obj.ns = which

    return obj

def get_subcommands(ns):
    obj = get_command(ns)
    return {attr[4:]: getattr(obj, attr) for attr in dir(obj)
            if attr.startswith('cmd_')}

def get_subcommand(ns, name):
    return get_subcommands(ns).get(name)

def resolve_command(cmd_):
    """Resolve the string `cmd_' into a (object, method) tuple."""
    try:
        if cmd_.find(':') < 0:
            cmd_ = 'system:%s' % cmd_

        ns, cmd_ = cmd_.split(':', 1)

        obj = get_command(ns)
        cmd = getattr(obj, 'cmd_%s' % cmd_)

        return obj, cmd, ns, cmd_
    except (KeyError, AttributeError):
        print('Error! command %s does not exist' % cmd_, file=sys.stderr)
        sys.exit(1)

def get_command_spec(cmd):
    """Get a command spec from the given (resolved) command, and
    distinguish default args vs. non-default args."""
    args, vararg, varkwarg, defvals = inspect.getargspec(cmd)

    assert varkwarg is None, 'Variable kwargs are not allowed in commands.'

    if args is None:
        args = tuple()
    if defvals is None:
        defvals = tuple()

    # Avoid the self argument.
    if isinstance(cmd, types.MethodType):
        args = args[1:]

    nargs = len(args) - len(defvals)
    args = list(zip(args[:nargs], [sys.intern('default')]*nargs)) + list(zip(args[nargs:], defvals))

    return args, vararg

class System(object):
    ns = 'system'
    descr = 'system commands'

    def cmd_help(self, which=None):
        """
        provides help for commands, when specified, `which' can be one
        either a namespace or a namespace:command tuple.
        """
        if which is None:
            print('Available namespaces')
            for obj in list(get_commands().values()):
                print(' ', obj.ns.ljust(20), '-', obj.descr)
        elif which.find(':') < 0:
            if which in get_commands():
                obj = get_commands()[which]

                print(which, '-', obj.descr)

                for k in [k for k in dir(obj) if k.startswith('cmd_')]:
                    cmd = '%s:%s' % (which, k[4:])
                    print_help_for_cmd(cmd, prefix='  ')
            else:
                print_help_for_cmd('system:%s' % which)
        else:
            print_help_for_cmd(which)
