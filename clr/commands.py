from __future__ import print_function
from importlib import import_module
from dataclasses import dataclass
import inspect
from inspect import Signature
import sys
import textwrap
import types
import difflib
import shelve
import os
from collections import namedtuple

import clr.config

# Sentinal for args get in get_command_spec to indicate there is no default.
# Because we are pickling command specs for clr cache use a random int
# and check for equality rather than object identity.
# TODO(michael.cusack): Move command spec to inspect.Signature and remove this.
NO_DEFAULT = 4194921784511160246

# Sorted list of command namespace keys.
NAMESPACE_KEYS = sorted(clr.config.commands().keys() | {'system'})

# Load lazily namespace modules as needed. Some have expensive/occasionally
# failing initialization.
__namespaces = {}

def _load_namespace(key):
    """Imports the module specified by the given key."""
    if key == 'system':
        instance = System()
    else:
        module_path = clr.config.commands()[key]
        try:
            module = import_module(module_path)
            instance = module.COMMANDS
        except Exception as e:
            return ErrorLoadingNamespace(key, e)
    descr = instance.descr
    longdescr = instance.longdescr if hasattr(instance, 'longdescr') else descr
    command_callables = {a[4:]: getattr(instance, a) for a in dir(instance) if a.startswith('cmd_')}
    command_specs = {n: get_command_spec(c) for n, c in command_callables.items()}
    return Namespace(descr, longdescr, command_specs, command_callables)

def get_namespace(namespace_key):
    """Lazily load and return the namespace"""
    global __namespaces
    if namespace_key not in __namespaces:
        __namespaces[namespace_key] = _load_namespace(namespace_key)
    return __namespaces[namespace_key]

def _get_close_matches(query, options):
    matches = difflib.get_close_matches(query, options, cutoff=.4)
    if query:
        matches.extend(sorted(o for o in options if o.startswith(query) and o not in matches))
    return matches

def resolve_command(query, cache=None):
    """Resolve the string `query' into a (namespace_key, command_name) tuple."""

    if ':' in query:
        namespace_key, command_name = query.split(':', 1)
    else:
        if query in get_namespace('system').commands:
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

    namespace = cache.get(namespace_key) if cache else get_namespace(namespace_key)
    if command_name not in namespace.commands:
        close_matches = _get_close_matches(command_name, namespace.commands)
        print(f"Error! Command '{command_name}' does not exist in namespace '{namespace_key}' - {namespace.descr}.\nClosest matches: {close_matches}\n\nAvailable commands: {namespace.commands}", file=sys.stderr)
        sys.exit(1)

    return namespace_key, command_name

CommandSpec = namedtuple('CommandSpec', 'args varargs docstr')
def get_command_spec(command_callable):
    """Get a command spec from the given (resolved) command, and
    distinguish default args vs. non-default args."""

    # TODO(michael.cusack): Move to using Signature and remove deprecated
    # getargspec.
    args, vararg, varkwarg, defvals = inspect.getargspec(command_callable)
    signature = Signature.from_callable(command_callable)

    if signature.return_annotation != Signature.empty:
        print(f'WARNING: {command_callable} returns a {signature.return_annotation} which is ignored.')
    for param in signature.parameters.values():
        if param.kind == param.VAR_KEYWORD:
            print(f'WARNING: Ignoring kwargs found for clr command {param} {command_callable}: {varkwarg}')

    if args is None:
        args = tuple()
    if defvals is None:
        defvals = tuple()

    # Avoid the self argument.
    if isinstance(command_callable, types.MethodType):
        args = args[1:]

    nargs = len(args) - len(defvals)
    args = list(zip(args[:nargs], [NO_DEFAULT]*nargs)) + list(zip(args[nargs:], defvals))
    return CommandSpec(args, vararg, inspect.getdoc(command_callable))


@dataclass
class Namespace:
    descr: str
    longdescr: str
    command_specs: dict
    command_callables: dict

    @property
    def commands(self):
        return sorted(self.command_specs.keys())

@dataclass
class ErrorLoadingNamespace:
    """Psuedo namespace for when one can't be loaded to show the error message."""
    key: str
    error: Exception

    commands = {}
    command_specs = {}

    @property
    def descr(self):
        return f"ERROR Could not load. See `clr help {self.key}`"

    @property
    def longdescr(self):
        return f"Error importing module '{clr.config.commands()[self.key]}' for namespace '{self.key}':\n\n{self.error}"

@dataclass(frozen=True)
class NamespaceCacheEntry:
    descr: str
    longdescr: str
    command_specs: dict

    @staticmethod
    def create(namespace):
        return NamespaceCacheEntry(namespace.descr, namespace.longdescr, namespace.command_specs)

    @property
    def commands(self):
        return sorted(self.command_specs.keys())

class NamespaceCache:
    """Cache introspection on command names and signatures to disk.

    This allows subsequent calls to `clr help` or `clr completion` to be fast.
    Necessary to work the fact that many clr command namespace modules import
    the world and initialize state on import.
    """

    def __init__(self):
        self.CACHE_FN = '/tmp/clr_command_cache'
        self.cache = shelve.open(self.CACHE_FN)

    def get(self, namespace_key):
        # Don't cache the system namespace. It is already loaded.
        if namespace_key == 'system': return get_namespace('system')
        if namespace_key not in self.cache:
            namespace = get_namespace(namespace_key)
            if isinstance(namespace, ErrorLoadingNamespace): return namespace
            self.cache[namespace_key] = NamespaceCacheEntry.create(namespace)
            self.cache.sync()
        return self.cache[namespace_key]

class System(object):
    """System namespace for the clr tool.

    Commands defined here will be avaliable directly without specifying a
    namespace. For example `clr help` instead of `clr system:help`. Be careful
    not to define commands here that have the same name as a defined namespace
    or it may be obscured."""

    descr = 'clr built-in commands'

    cache = NamespaceCache()

    def cmd_clear_cache(self):
        """Clear clr's cache.

        clr caches command specs to disk to speed up help and completions.
        Run this to clear the cache if your results are stale."""
        # Remove file. Process exits after this, will get recreated on next run.
        os.remove(self.cache.CACHE_FN)

    def cmd_completion(self, query=''):
        """Completion results for first arg to clr."""

        results = []
        if ':' not in query:
            # Suffix system commands with a space.
            results.extend(f'{c} ' for c in self.cache.get('system').commands)
            # Suffix namespaces with a :.
            results.extend(f'{k}:' for k in NAMESPACE_KEYS)
        else:
            namespace_key, _ = query.split(':', 1)
            results.extend(f'{namespace_key}:{c} ' for c in self.cache.get(namespace_key).commands)

        print('\n'.join(r for r in results if r.startswith(query)), end='')

    def cmd_profile_imports(self, *namespaces):
        """Prints some debugging information about how long it takes to import clr namespaces."""
        import time

        if not namespaces: namespaces = NAMESPACE_KEYS
        results = {}
        for index, key in enumerate(namespaces):
            t1 = time.time()
            get_namespace(key)
            results[f'#{index + 1}-{key}'] = time.time() - t1

        print('\n'.join(f'{k}: {int(1000*v)}' for k, v in sorted(results.items(), key=lambda i:i[1])))

    def cmd_help(self, query=None, query2=None):
        """
        provides help for commands, when specified, `query' can be one
        either a namespace or a namespace:command tuple.
        """
        if not query:
            print('Available namespaces')
            for namespace_key in NAMESPACE_KEYS:
                print(' ', namespace_key.ljust(20), '-', self.cache.get(namespace_key).descr)
            return

        # If they passed just one arg and it is a namespace key, print help for the full namespace.
        if query.endswith(':'): query = query[:-1]
        if query in NAMESPACE_KEYS and not query2:
            for command in self.cache.get(query).commands:
                self.print_help_for_command(query, command, prefix='  ')
            return

        if query2: query = f'{query}:{query2}'
        namespace_key, command_name = resolve_command(query, cache=self.cache)
        self.print_help_for_command(namespace_key, command_name)

    def print_help_for_command(self, namespace_key, command_name, prefix=''):
        w = textwrap.TextWrapper(
            initial_indent=prefix, subsequent_indent=prefix,
            width=70)

        spec, vararg, docstr = self.cache.get(namespace_key).command_specs[command_name]

        def is_default(spec):
            # print(f'{spec} {NO_DEFAULT} {spec[1] is NO_DEFAULT} {spec[1] == NO_DEFAULT}')
            return spec[1] == NO_DEFAULT
        req = [spec_item for spec_item in spec if is_default(spec_item)]
        notreq = [spec_item for spec_item in spec if not is_default(spec_item)]

        args = []
        if len(req) > 0:
            args.append(' '.join(['<%s>' % a for a, _ in req]))

        if notreq:
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

        if docstr:
            for l in docstr.split('\n'):
                print(w.fill(l))


