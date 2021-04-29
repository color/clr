from __future__ import print_function
from importlib import import_module
from builtins import zip
from builtins import object
from past.builtins import intern
from dataclasses import dataclass
from typing import Tuple
import inspect
import sys
import textwrap
import types
import difflib
import shelve

import clr.config

NAMESPACE_KEYS = sorted(clr.config.commands().keys() | {'system'})
# Load lazily namespace modules as needed. Some have expensive/occasionally
# failing initialization.
__namespaces = {}

def get_namespaces():
    # Fill namespace cache
    for key in NAMESPACE_KEYS: get_namespace(key)
    return __namespaces

def _load_namespace(key):
    if key == 'system':
        return System()

    module_path = clr.config.commands()[key]
    try:
        module = import_module(module_path)
        return module.COMMANDS
    except Exception as e:
        return ErrorLoadingNamespace(key, e)

def get_namespace(namespace_key):
    """Lazily load and return the namespace"""
    global __namespaces
    if namespace_key not in __namespaces:
        __namespaces[namespace_key] = _load_namespace(namespace_key)
    return __namespaces[namespace_key]

def list_commands(namespace_key):
    return sorted(attr[4:] for attr in dir(get_namespace(namespace_key)) if attr.startswith('cmd_'))

def get_command(namespace_key, command_name):
    return getattr(get_namespace(namespace_key), f'cmd_{command_name}')

def _get_close_matches(query, options):
    matches = difflib.get_close_matches(query, options, cutoff=.4)
    if query:
        matches.extend(sorted(o for o in options if o.startswith(query) and o not in matches))
    return matches

def resolve_command(query, cache=None):
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

    if namespace_key not in NAMESPACE_KEYS:
        close_matches = _get_close_matches(namespace_key, NAMESPACE_KEYS)
        print(f"Error! Command namespace '{namespace_key}' does not exist.\nClosest matches: {close_matches}\n\nAvailable namespaces: {sorted(NAMESPACE_KEYS)}", file=sys.stderr)
        sys.exit(1)

    commands = cache[namespace_key].commands.keys() if cache else list_commands(namespace_key)
    if command_name not in commands:
        close_matches = _get_close_matches(command_name, commands)
        namespace_descr = cache[namespace_key].descr if cache else get_namespace(namespace_key).descr
        print(f"Error! Command '{command_name}' does not exist in namespace '{namespace_key}' - {namespace.descr}.\nClosest matches: {close_matches}\n\nAvailable commands: {commands}", file=sys.stderr)
        sys.exit(1)

    return namespace_key, command_name

def get_command_spec(cmd):
    """Get a command spec from the given (resolved) command, and
    distinguish default args vs. non-default args."""
    args, vararg, varkwarg, defvals = inspect.getargspec(cmd)

    if varkwarg is not None:
        print(f'WARNING: Ignoring kwargs found for clr command {cmd}: {varkwarg}')

    if args is None:
        args = tuple()
    if defvals is None:
        defvals = tuple()

    # Avoid the self argument.
    if isinstance(cmd, types.MethodType):
        args = args[1:]

    nargs = len(args) - len(defvals)
    args = list(zip(args[:nargs], [intern('default')]*nargs)) + list(zip(args[nargs:], defvals))

    return args, vararg, inspect.getdoc(cmd)

@dataclass(frozen=True)
class NamespaceCacheEntry:
    commands: dict
    descr: str
    longdescr: str

class System(object):
    """System namespace for the clr tool.

    Commands defined here will be avaliable directly without specifying a
    namespace. For example `clr help` instead of `clr system:help`. Be careful
    not to define commands here that have the same name as a defined namespace
    or it may be obscured."""

    descr = 'clr built-in commands'

    # Cache introspection on cmd names and signatures to disk to that
    # subsequent calls to `clr help` or `clr completion` are fast.
    # Work around for our super slow import times.
    # Delete this file to clear the cache.
    cache = shelve.open('/tmp/clr_cache')

    def _list_commands(self, namespace_key):
        """Cached `list_commands`"""
        return self._get_or_fill_cache(namespace_key).commands.keys()

    def _get_or_fill_cache(self, namespace_key):
        """Cached `list_commands`"""
        if namespace_key not in self.cache:
            namespace = get_namespace(namespace_key)
            if isinstance(namespace_key, ErrorLoadingNamespace): return

            longdescr = namespace.longdescr if hasattr(namespace, 'longdescr') else namespace.descr
            commands = {c: get_command_spec(get_command(namespace_key, c)) for c in list_commands(namespace_key)}
            self.cache[namespace_key] = NamespaceCacheEntry(commands, namespace.descr, longdescr)
            self.cache.sync()
        return self.cache[namespace_key]

    def cmd_completion(self, query=''):
        results = []

        if ':' not in query:
            # Suffix system commands with a space.
            results.extend(f'{c} ' for c in list_commands('system'))
            # Suffix namespaces with a :.
            results.extend(f'{k}:' for k in NAMESPACE_KEYS)
        else:
            namespace_key, _ = query.split(':', 1)
            results.extend(f'{namespace_key}:{c} ' for c in self._list_commands(namespace_key))

        print('\n'.join(r for r in results if r.startswith(query)), end='')

    def cmd_profile_imports(self, *namespaces):
        import time

        if not namespaces: namespaces = NAMESPACE_KEYS
        results = {}
        for index, key in enumerate(namespaces):
            t1 = time.time()
            get_namespace(key)
            results[f'{index}-{key}'] = time.time() - t1

        print('\n'.join(f'{k}: {int(1000*v)}' for k, v in sorted(results.items(), key=lambda i:i[1])))

    def cmd_help(self, query=None, query2=None):
        """
        provides help for commands, when specified, `query' can be one
        either a namespace or a namespace:command tuple.
        """
        if not query:
            print('Available namespaces')
            for namespace_key in NAMESPACE_KEYS:
                entry = self._get_or_fill_cache(namespace_key)
                print(' ', namespace_key.ljust(20), '-', entry.descr)
            return

        # If they passed just one arg and it is a namespace key, print help for the full namespace.
        if query in NAMESPACE_KEYS and not query2:
            entry = self._get_or_fill_cache(query)
            print(query, '-', entry.longdescr)

            for command in entry.commands:
                self.print_help_for_command(query, command, prefix='  ')
            return

        if query2: query = f'{query}:{query2}'
        namespace_key, command_name = resolve_command(query, cache=self.cache)
        self.print_help_for_command(namespace_key, command_name)

    def print_help_for_command(self, namespace_key, command_name, prefix=''):
        w = textwrap.TextWrapper(
            initial_indent=prefix, subsequent_indent=prefix,
            width=70)

        spec, vararg, docstr = self._get_or_fill_cache(namespace_key).commands[command_name]

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

        if docstr is not None:
            for l in docstr.split('\n'):
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
