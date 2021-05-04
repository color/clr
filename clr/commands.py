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
import argparse

import clr.config

CommandSpec = namedtuple('CommandSpec', 'docstr signature')

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
    # Prefer doc string, otherwise explicit .longdescr, otherwise .descr
    longdescr = inspect.getdoc(instance) or getattr(instance, 'longdescr', descr)
    command_callables = {
        attribute_name[4:]: getattr(instance, attribute_name)
        for attribute_name in dir(instance)
        if attribute_name.startswith('cmd_')
    }
    command_specs = {
        command_name:  CommandSpec(
            inspect.getdoc(command_callable),
            Signature.from_callable(command_callable))
        for command_name, command_callable in command_callables.items()
    }
    return Namespace(
        key, descr, longdescr, command_specs, command_callables, instance)

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
        print(f'See `clr help {namespace_key}` for details.')
        sys.exit(1)

    return namespace_key, command_name

@dataclass
class Namespace:
    key: str
    descr: str
    longdescr: str
    command_specs: Dict[str, CommandSpec]
    command_callables: Dict[str, Callable]
    instance: any

    @property
    def commands(self):
        """Sorted list of command names in this namespace."""
        return sorted(self.command_specs.keys())

    def arguement_parser(self, command_name):
        """Returns an ArgumentParser matching the signature of command."""
        spec = self.command_specs[command_name]
        parser = argparse.ArgumentParser(
            prog=f'clr {self.key}:{command_name}',
            description=spec.docstr if spec.docstr else '',
            add_help=False,
            formatter_class=argparse.RawDescriptionHelpFormatter)
        for param in spec.signature.parameters.values():
            positional = param.default == Signature.empty

            if positional:
                if param.kind in (param.POSITIONAL_ONLY, param.POSITIONAL_OR_KEYWORD):
                    parser.add_argument(param.name, type=str)
                elif param.kind == param.VAR_POSITIONAL:
                    parser.add_argument(param.name, type=str, nargs='*')
                else:
                    raise AssertionError(f'Unexpected kind of positional param {param.name} in {command_name}: {repr(param.kind)}')
            else:
                help_text = f"Defaults to {param.name}='{param.default}'"
                default_type = str
                if param.default is not None:
                    default_type = type(param.default)
                if default_type not in (str, bool, int, float):
                    raise AssertionError(f'Unexpected arg type for {param.name} in {command_name}: {default_type}')

                arg_name = f'--{param.name}'

                if default_type == bool:
                    group = parser.add_mutually_exclusive_group()
                    group.add_argument(arg_name, help=help_text, default=param.default,
                        dest=param.name, action='store_true')
                    group.add_argument(f'--no{param.name}', help=help_text, dest=param.name,
                        action='store_false')
                else:
                    group = parser.add_mutually_exclusive_group()
                    group.add_argument(param.name, nargs='?', help=help_text, type=default_type, default=param.default)
                    group.add_argument(arg_name, help=help_text, type=default_type, default=param.default)
        return parser


@dataclass
class ErrorLoadingNamespace:
    """Psuedo namespace for when one can't be loaded to show the error message."""
    key: str
    error: Exception

    @property
    def commands(self):
        return tuple()

    @property
    def command_specs(self):
        return {}

    @property
    def descr(self):
        return f"ERROR Could not load. See `clr help {self.key}`"

    @property
    def longdescr(self):
        return f"Error importing module '{NAMESPACE_MODULE_PATHS[self.key]}' for namespace '{self.key}':\n\n{self.error}"

@dataclass(frozen=True)
class NamespaceCacheEntry:
    key: str
    descr: str
    longdescr: str
    command_specs: dict

    @staticmethod
    def create(namespace):
        return NamespaceCacheEntry(namespace.key, namespace.descr,
            namespace.longdescr, namespace.command_specs)

# Steal some functionality.
NamespaceCacheEntry.commands = Namespace.commands
NamespaceCacheEntry.arguement_parser = Namespace.arguement_parser


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

    def cmd_completion2(self, command_name, query=''):
        namespace_key, command_name = resolve_command(command_name, cache=self.cache)
        parser = self.cache.get(namespace_key).arguement_parser(command_name)
        print(parser)

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
            print(f'{query} - {namespace.longdescr}\n')
            for command in namespace.commands:
                print('-' * 80)
                self.print_help_for_command(query, command)
            return

        if query2:
            query = f'{query}:{query2}'
        namespace_key, command_name = resolve_command(query, cache=self.cache)
        self.print_help_for_command(namespace_key, command_name)

    def print_help_for_command(self, namespace, command):
        try:
            self.cache.get(namespace).arguement_parser(command).print_help()
        except BrokenPipeError:
            # Less noisy if help is piped to `head`, etc.
            pass
