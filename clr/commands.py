from __future__ import print_function
from importlib import import_module
from builtins import zip
from builtins import object
from past.builtins import intern
from dataclasses import dataclass
import inspect
import sys
import textwrap
import types
import difflib

import clr.config

NAMESPACE_KEYS = clr.config.commands().keys() | {'system'}
# Load lazily namespace modules as needed. Some have expensive/occasionally
# failing initialization.
__namespaces = {}

def get_command_spec(command):
    """Get a command spec from the given (resolved) command, and
    distinguish default args vs. non-default args."""
    args, vararg, varkwarg, defvals = inspect.getargspec(command)

    assert varkwarg is None, 'Variable kwargs are not allowed in commands.'

    if args is None:
        args = tuple()
    if defvals is None:
        defvals = tuple()

    # Avoid the self argument.
    if isinstance(command, types.MethodType):
        args = args[1:]

    nargs = len(args) - len(defvals)
    args = list(zip(args[:nargs], [intern('default')]*nargs)) + list(zip(args[nargs:], defvals))

    return args, vararg

def get_namespaces():
    # Fill namespace cache
    for key in NAMESPACE_KEYS: get_namespace(key)
    return __namespaces

def has_namespace(key):
    return key in NAMESPACE_KEYS

def load_namespace(key):
    if key == 'system':
        obj = System()
    else:
        mod_path = clr.config.commands()[key]
        try:
           module = import_module(mod_path)
           obj = module.COMMANDS
        except Exception as e:
            print(f"WARNING: Loading namespace '{key}' failed: {e}")
            obj = ErrorLoadingNamespace(key, e)

    return obj

def get_namespace(namespace):
    global __namespaces
    if namespace not in __namespaces:
        __namespaces[namespace] = load_namespace(namespace)
    return __namespaces[namespace]

def list_commands(namespace_key):
    return sorted(attr[4:] for attr in dir(get_namespace(namespace_key)) if attr.startswith('cmd_'))

def get_command(namespace_key, command_name):
    return getattr(get_namespace(namespace_key), f'cmd_{command_name}')

def _get_close_matches(query, options):
    matches = difflib.get_close_matches(query, options, cutoff=.4)
    if not matches:
        matches = sorted(o for o in options if o.startswith(query))
    return matches

def resolve_command(query):
    """Resolve the string `query' into a (namespace_key, command_name, namespace, method) tuple."""

    if ':' in query:
        namespace_key, command_name = query.split(':', 1)
    else:
        if query in list_commands('system'):
            # So that `clr help` works as expected.
            namespace_key = 'system'
            command_name = query
        else:
            # This will still fail, but the error messages will be sensible.
            namespace_key = query
            command_name = ''

    if not has_namespace(namespace_key):
        close_matches = _get_close_matches(namespace_key, NAMESPACE_KEYS)
        print(f"Error! Command namespace '{namespace_key}' does not exist.\nClosest matches: {close_matches}\n\nAvaliable namespaces: {sorted(NAMESPACE_KEYS)}", file=sys.stderr)
        sys.exit(1)

    commands = list_commands(namespace_key)
    if command_name not in commands:
        close_matches = _get_close_matches(command_name, commands)
        print(f"Error! Command '{command_name} does not exist in namespace '{namespace_key}'.\nClosest matches: {close_matches}\n\nAvaliable commands: {commands}", file=sys.stderr)
        sys.exit(1)

    return get_namespace(namespace_key), get_command(namespace_key, command_name), namespace_key, command_name

class System(object):
    """System namespace for the clr tool.

    Commands defined here will be avaliable directly without specifying a
    namespace. For example `clr help` instead of `clr system:help`. Be careful
    not to define commands here that have the same name as a defined namespace
    or it may be obscured."""

    descr = 'system commands'

    def cmd_help(self, query=None, query2=None):
        """
        provides help for commands, when specified, `query' can be one
        either a namespace or a namespace:command tuple.
        """
        if not query:
            print('Available namespaces')
            for key, namespace in get_namespaces().items():
                print(' ', key.ljust(20), '-', namespace.descr)
            return

        # If they passed just one arg and it is a namespace key, print help for the full namespace.
        if query in NAMESPACE_KEYS and not query2:
            namespace = get_namespace(query)
            descr = namespace.longdescr if hasattr(namespace, 'longdescr') else namespace.descr
            print(query, '-', descr)

            for command in list_commands(query):
                self.print_help_for_command(query, command, prefix='  ')
            return

        if query2: query = f'{query}:{query2}'
        _, _, namespace_key, command_name = resolve_command(query)
        self.print_help_for_command(namespace_key, command_name)

    def print_help_for_command(self, namespace_key, command_name, prefix=''):
        w = textwrap.TextWrapper(
            initial_indent=prefix, subsequent_indent=prefix,
            width=70)

        command = get_command(namespace_key, command_name)

        spec, vararg = get_command_spec(command)

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

        print(w.fill('%s %s' % (command_name, ' '.join(args))))

        w.initial_indent += '  '
        w.subsequent_indent += '  '

        doc = inspect.getdoc(command)
        if doc is not None:
            for l in doc.split('\n'):
                print(w.fill(l))

@dataclass
class ErrorLoadingNamespace:
    """Psuedo namespace for when one can't be loaded to show the error message."""
    key: str
    error: Exception

    @property
    def descr(self):
        return f"ERROR Could not load. See `clr help {self.key}`"

    @property
    def longdescr(self):
        return f"Error importing module '{clr.config.commands()[self.key]}' for namespace '{self.key}':\n\n{self.error}"
