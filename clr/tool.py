"""command/command line interface to color things.

  $ clr help
  Available namespaces
    www                  - www server commands
    django               - django commands
    pg                   - postgres commands

  $ clr help django
      django - django commands
        django:migrate [args...]
          Run south migration
        django:reset [args...]
          Reset an application
        django:syncdb [args...]
          Do a syncdb. You probably want django:migrate instead.
        django:test [args...]
          Run django tests

  $ clr django:syncdb
      Syncing...
      Creating tables ...
      Installing custom SQL ...
      Installing indexes ...
      Installed 0 object(s) from 0 fixture(s)

      Synced:
       > django.contrib.auth
       > django.contrib.contenttypes
       > django.contrib.sessions
       > django.contrib.sites
       > django.contrib.messages
       > django.contrib.staticfiles
       > south

      Not synced (use migrations):
       - django_apps.core
      (use ./manage.py migrate to migrate these)
"""

from __future__ import absolute_import

from collections import defaultdict
from copy import deepcopy
import imp
import inspect
import optparse
import sys
import textwrap
import types

import clr
from clr.config import CONFIG


def print_help_for_cmd(cmd_, prefix=''):
    w = textwrap.TextWrapper(
        initial_indent=prefix, subsequent_indent=prefix,
        width=70)

    _, cmd, _, _ = resolve_command(cmd_)

    spec, vararg = get_command_spec(cmd)

    is_default = lambda (a, s): s is intern('default')
    req = [spec_item for spec_item in spec if is_default(spec_item)]
    noreq = [spec_item for spec_item in spec if not is_default(spec_item)]

    args = []
    if len(req) > 0:
        args.append(' '.join(['<%s>' % a for a, _ in req]))

    if len(notreq) > 0:
        def atxt(a, v):
            if isinstance(v, types.BooleanType):
                if v:
                    return '--no%s' % a
                else:
                    return '--%s' % a

            else:
                return '--%s=%s' % (a, v)

        args.append('[%s]' % ' '.join([atxt(a, v) for a, v in notreq]))

    if vararg is not None:
        args.append('[%s...]' % vararg)

    print w.fill('%s %s' % (cmd_, ' '.join(args)))

    w.initial_indent += '  '
    w.subsequent_indent += '  '

    doc = inspect.getdoc(cmd)
    for l in doc.split('\n'):
        print w.fill(l)

class System(object):
    ns = 'system'
    descr = 'system commands'

    def cmd_help(self, which=None):
        """
        provides help for commands, when specified, `which' can be one
        either a namespace or a namespace:command tuple.
        """
        if which is None:
            print 'Available namespaces'
            for obj in get_commands().values():
                print ' ', obj.ns.ljust(20), '-', obj.descr
        elif which.find(':') < 0:
            if which in get_commands():
                obj = get_commands()[which]

                print which, '-', obj.descr

                for k in filter(lambda k: k.startswith('cmd_'), dir(obj)):
                    cmd = '%s:%s' % (which, k[4:])
                    print_help_for_cmd(cmd, prefix='  ')
            else:
                print_help_for_cmd('system:%s' % which)
        else:
            print_help_for_cmd(which)

def get_commands():
    cmds = dict((ns, get_command(ns)) for ns in CONFIG['commands'].keys())
    cmds['system'] = System()

    return cmds

def get_command(which):
    if which == 'system':
        obj = System()
    else:
        path = path_of_module(CONFIG['commands'][which])
        d    = {}
        execfile(path, d)
        obj = d['COMMANDS']

    # Backfill namespace.
    obj.ns = which

    return obj

def path_of_module(mod, path=None):
    a, b = peel(mod, '.')
    _, path, _ = imp.find_module(a, path)

    if b:
        return path_of_module(b, [path])
    else:
        return path

def peel(string, delimitter):
    peeled = string.split(delimitter, 1)
    if len(peeled) == 1:
        return peeled[0], ''
    else:
        return peeled[0], peeled[1]

def get_options():
    return [__import__(o, {}, {}, ['']).OPTIONS for o in CONFIG['options']]

def call(cmd_, *args, **kwargs):
    _, cmd, _, _ = resolve_command(cmd_)
    cmd(*args, **kwargs)

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
        print >>sys.stderr, 'Error! command %s does not exist' % cmd_
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
    args = zip(args[:nargs], [intern('default')]*nargs) + zip(args[nargs:], defvals)

    return args, vararg

def add_global_options(parser):
    for o in get_options():
        o.add_options(parser)

def handle_global_options(opts):
    hooks = defaultdict(lambda: [])

    for o in get_options():
        for hook, fun in (o.handle_options(opts) or {}).iteritems():
            hooks[hook].append(fun)

    return hooks

def main(argv):
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

if __name__ == '__main__':
    main(sys.argv)
