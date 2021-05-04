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
import time
from collections import namedtuple
from typing import Dict, Callable

import clr.config

# Sentinal for arg defaults in get_command_spec to indicate there is no default.
# Because we are pickling command specs for clr cache, use a random int and
# check for equality rather than object identity.
# TODO(michael.cusack): Move command spec to inspect.Signature and remove this.
NO_DEFAULT = 4194921784511160246

NAMESPACE_MODULE_PATHS = clr.config.read_namespaces()
# Sorted list of command namespace keys.
NAMESPACE_KEYS = sorted({'system', *NAMESPACE_MODULE_PATHS.keys()})

# Load lazily namespace modules as needed. Some have expensive/occasionally
# failing initialization.
__NAMESPACES = {}

def _load_namespace(key):
    """Imports the module specified by the given key."""
    if key == 'system':
        # Defined at end of file.
        instance = System()
    else:
        module_path = NAMESPACE_MODULE_PATHS[key]
        try:
            module = import_module(module_path)
        except Exception as error:
            return ErrorLoadingNamespace(key, error)
        instance = module.COMMANDS
    descr = instance.descr
    longdescr = getattr(instance, 'longdescr', descr)
    command_callables = {
        attribute_name[4:]: getattr(instance, attribute_name)
        for attribute_name in dir(instance)
        if attribute_name.startswith('cmd_')
    }
    command_specs = {
        command_name: get_command_spec(command_callable)
        for command_name, command_callable in command_callables.items()
    }
    return Namespace(
        descr, longdescr, command_specs, command_callables, instance)

def get_namespace(namespace_key):
    """Lazily load and return the namespace"""
    global __NAMESPACES
    if namespace_key not in __NAMESPACES:
        __NAMESPACES[namespace_key] = _load_namespace(namespace_key)
    return __NAMESPACES[namespace_key]

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
    command_specs: Dict[str, CommandSpec]
    command_callables: Dict[str, Callable]
    instance: any

    @property
    def commands(self):
        return sorted(self.command_specs.keys())

@dataclass
class ErrorLoadingNamespace:
    """Psuedo namespace for when one can't be loaded to show the error message."""
    key: str
    error: Exception

    # Satisfy the same properties of a `Namespace`, but never have any actual
    # commands.
    commands = frozenset()
    command_specs = {}

    @property
    def descr(self):
        return f"ERROR Could not load. See `clr help {self.key}`"

    @property
    def longdescr(self):
        return f"""Error importing module '{clr.config.commands()[self.key]}' for namespace '{self.key}':\n\n{self.error}"""

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
    Necessary to work around the fact that many clr command namespace modules
    import the world and initialize state on import.
    """

    def __init__(self):
        tmpdir = os.environ.get('TMPDIR', '/tmp')
        self.cache_fn = os.path.join(tmpdir, 'clr_command_cache')
        # Clr processes are short lived. We don't close the shelve, but are
        # careful to sync it after writes.
        self.cache = shelve.open(self.cache_fn)

    def get(self, namespace_key):
        # Don't cache the system namespace. It is already loaded.
        if namespace_key == 'system':
            return get_namespace('system')
        # Load namespace and save spec to the shelve.
        if namespace_key not in self.cache:
            namespace = get_namespace(namespace_key)
            if isinstance(namespace, ErrorLoadingNamespace):
                return namespace
            self.cache[namespace_key] = NamespaceCacheEntry.create(namespace)
            self.cache.sync()
        return self.cache[namespace_key]

class System:
    """Namespace for system commands in the clr tool.

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
        os.remove(self.cache.cache_fn)

    def cmd_completion1(self, query=''):
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
        if not namespaces:
            namespaces = NAMESPACE_KEYS
        results = {}
        for index, key in enumerate(namespaces):
            start_time = time.time()
            get_namespace(key)
            results[f'#{index + 1}-{key}'] = time.time() - start_time

        print('\n'.join(f'{k}: {int(1000*v)}'
                        for k, v in sorted(results.items(), key=lambda i:i[1])))

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
        if query.endswith(':'):
            query = query[:-1]
        if query in NAMESPACE_KEYS and not query2:
            namespace = self.cache.get(query)
            print(query, '-', namespace.longdescr)
            for command in namespace.commands:
                self.print_help_for_command(query, command, prefix='  ')
            return

        if query2:
            query = f'{query}:{query2}'
        namespace_key, command_name = resolve_command(query, cache=self.cache)
        self.print_help_for_command(namespace_key, command_name)

    def print_help_for_command(self, namespace_key, command_name, prefix=''):
        width = os.get_terminal_size().columns
        text_wrapper = textwrap.TextWrapper(
            initial_indent=prefix, subsequent_indent=prefix, width=width)

        spec, vararg, docstr = self.cache.get(namespace_key).command_specs[command_name]

        def is_default(spec):
            return spec[1] == NO_DEFAULT
        req = [spec_item for spec_item in spec if is_default(spec_item)]
        notreq = [spec_item for spec_item in spec if not is_default(spec_item)]

        args = []
        if len(req) > 0:
            args.append(' '.join(['<%s>' % a for a, _ in req]))

        if notreq:
            def arg_text(arg_name, default_value):
                if isinstance(default_value, bool):
                    if default_value:
                        return f'--no{arg_name}'
                    return f'--{arg_name}'
                return f'--{arg_name}={default_value}'
            arg_texts = [arg_text(arg_name, default_value) for arg_name, default_value in notreq]
            args.append('[%s]' % ' '.join(arg_texts))

        if vararg is not None:
            args.append('[%s...]' % vararg)

        print(text_wrapper.fill('%s %s' % (command_name, ' '.join(args))))

        text_wrapper.initial_indent += '  '
        text_wrapper.subsequent_indent += '  '

        if docstr:
            for line in docstr.split('\n'):
                print(text_wrapper.fill(line))
