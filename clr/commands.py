from __future__ import print_function
from importlib import import_module
from builtins import zip
from builtins import object
from past.builtins import intern
import inspect
import sys
import textwrap
import types
import difflib

import clr.config
from clr.util import path_of_module

# Load lazily
__namespaces = {}

def print_help_for_cmd(cmd_, prefix=''):
    w = textwrap.TextWrapper(
        initial_indent=prefix, subsequent_indent=prefix,
        width=70)

    _, cmd, _, _ = resolve_command(cmd_)

    spec, vararg = get_command_spec(cmd)

    is_default = lambda a_s: a_s[1] is intern('default')
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
    if doc is not None:
        for l in doc.split('\n'):
            print(w.fill(l))

NAMESPACE_KEYS = clr.config.commands().keys() | {'system'}

def get_namespaces():
    # Fill namespace cache
    for namespace in NAMESPACE_KEYS: get_namespace(namespace)
    return __namespaces

def has_namespace(namespace):
    return namespace in NAMESPACE_KEYS

def load_namespace(namespace):
    if namespace == 'system':
        obj = System()
    else:
        mod_path = clr.config.commands()[namespace]
        x = import_module(mod_path)
        obj = x.COMMANDS

    # Backfill namespace.
    obj.ns = obj.namespace = namespace
    return obj

def get_namespace(namespace):
    global __namespaces
    if namespace not in __namespaces:
        __namespaces[namespace] = load_namespace(namespace)
    return __namespaces[namespace]

def get_subcommands(namespace):
    obj = get_namespaces(namespace)
    return {attr[4:]: getattr(obj, attr) for attr in dir(obj)
            if attr.startswith('cmd_')}

def get_subcommand(namespace, name):
    return get_subcommands(namespace).get(name)

def resolve_command(query):
    """Resolve the string `cmd_' into a (object, method) tuple."""
    if ':' not in query: query = f'system:{query}'

    namespace_key, cmd_name = query.split(':', 1)
    method_name = f'cmd_{cmd_name}'

    if not has_namespace(namespace_key):
        close_matches = difflib.get_close_matches(namespace_key, NAMESPACE_KEYS, cutoff=.4)
        print(f"Error! Command namespace '{namespace_key}' does not exist.\nClosest matches: {close_matches}\n\nAvaliable namespaces: {sorted(NAMESPACE_KEYS)}", file=sys.stderr)
        sys.exit(1)

    namespace = get_namespace(namespace_key)

    if not hasattr(namespace, method_name):
        cmds = sorted(_[4:] for _ in dir(namespace) if _.startswith('cmd_'))
        close_matches = difflib.get_close_matches(cmd_name, cmds, cutoff=.4)
        print(f"Error! Command '{cmd_name}'' does not exist in '{namespace_key}'.\nClosest matches: {close_matches}\n\nAvaliable commands: {cmds}", file=sys.stderr)
        sys.exit(1)

    cmd = getattr(namespace, method_name)
    return namespace, cmd, namespace_key, cmd_name

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
    args = list(zip(args[:nargs], [intern('default')]*nargs)) + list(zip(args[nargs:], defvals))

    return args, vararg

class System(object):
    namespace = 'system'
    descr = 'system commands'

    def cmd_help(self, which=None):
        """
        provides help for commands, when specified, `which' can be one
        either a namespace or a namespace:command tuple.
        """
        if which is None:
            print('Available namespaces')
            for obj in list(get_commands().values()):
                print(' ', obj.namespace.ljust(20), '-', obj.descr)
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
