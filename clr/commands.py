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
from typing import Dict, Callable, Any
import argparse

import clr.config

NAMESPACE_MODULE_PATHS = clr.config.read_namespaces()
# Sorted list of command namespace keys.
NAMESPACE_KEYS = sorted({'system', *NAMESPACE_MODULE_PATHS.keys()})

# Load lazily namespace modules as needed. Some have expensive/occasionally
# failing initialization.
__NAMESPACES = {}

def _load_namespace(key):
    """Imports a namespace module."""
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
    # Build CommandSpecs for each command. These contain metadata about the
    # command and its args. These are kept in a seperate dataclass from the
    # callables because CommandSpec's are pickle-able and cached to disk.
    command_specs = {}
    for command_name, command_callable in command_callables.items():
        docstr = inspect.getdoc(command_callable)
        if docstr is None:
            docstr = ''
        command_specs[command_name] = CommandSpec(
            docstr,
            Signature.from_callable(command_callable))

    return Namespace(key=key, descr=descr, longdescr=longdescr, command_specs=command_specs,
        command_callables=command_callables, instance=instance)

def get_namespace(namespace_key):
    """Lazily load and return a namespace"""
    global __NAMESPACES
    if namespace_key not in __NAMESPACES:
        __NAMESPACES[namespace_key] = _load_namespace(namespace_key)
    return __NAMESPACES[namespace_key]

def _get_close_matches(query, options):
    """Utility function for making suggests when `resolve_command` can't resolve a namespace/command
    name."""
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
            # System commands can be referred to w/o a namespace so that `clr help` works as
            # expected.
            namespace_key = 'system'
            command_name = query
        else:
            # This will still fail, but the error messages will be sensible.
            namespace_key = query
            command_name = ''

    if namespace_key not in NAMESPACE_KEYS:
        print(f"Error! Command namespace '{namespace_key}' does not exist.\nClosest matches: "
              f"{_get_close_matches(namespace_key, NAMESPACE_KEYS)}\n\nAvailable namespaces: "
              f"{NAMESPACE_KEYS}", file=sys.stderr)
        sys.exit(1)

    namespace = cache.get(namespace_key) if cache else get_namespace(namespace_key)
    if command_name not in namespace.commands:
        print(f"Error! Command '{command_name}' does not exist in namespace '{namespace_key}' - "
              f"{namespace.descr}.\nClosest matches: "
              f"{_get_close_matches(command_name, namespace.commands)}\n\nAvailable commands: "
              f"{namespace.commands}\nSee `clr help {namespace_key}` for details.", file=sys.stderr)
        sys.exit(1)

    return namespace_key, command_name

class NoneIgnoringArgparseDestination(argparse.Namespace):
    """argparse destination namespace that ignores attributes changed to None.

    In order to allow arguments to be specified as positional or named (--a A) we add two mutally
    exlusive arguments with the same dest. The positional one has nargs=? which means when it is
    left out it will always set None. In practice there is no way to explicitly and purposfully set
    an argument to None, so we simply ignore attempts to set an attribute to None if is currently
    has a value. We are relying on the callable's Signature's BoundArguments to apply defaults, not
    argparse.
    """
    def __setattr__(self, attr, value):
        if value is not None:
            super().__setattr__(attr, value)

@dataclass
class CommandSpec:
    """Pickle-able specification of a command."""
    docstr: str
    signature: Signature

@dataclass
class Namespace:
    """clr command namespace."""
    key: str
    descr: str
    longdescr: str
    command_specs: Dict[str, CommandSpec]
    command_callables: Dict[str, Callable]
    instance: Any

    @property
    def commands(self):
        """Sorted list of command names in this namespace."""
        return sorted(self.command_specs.keys())

    def parse_args(self, command_name, argv):
        """Parse args for the given command."""

        signature = self.command_specs[command_name].signature
        # Parse the command line arguments, starting after command name.
        parsed = NoneIgnoringArgparseDestination()
        self.argument_parser(command_name).parse_args(sys.argv[2:], namespace=parsed)

        # Turn parsed args into something we can pass to signature.bind.
        args = []
        kwargs = {}
        for param in signature.parameters.values():
            value = getattr(parsed, param.name, None)
            if param.kind  == param.POSITIONAL_ONLY:
                args.append(value)
            elif param.kind == param.VAR_POSITIONAL:
                args.extend(value)
            elif param.kind in (param.KEYWORD_ONLY, param.POSITIONAL_OR_KEYWORD):
                if param.default != param.empty and value is None:
                    # BoundArguments will apply the defaults.
                    continue
                kwargs[param.name] = value

        # Ensure the signature is valid and applies default. Could use argparse to do more of this,
        # but adds correctness guarantees and gives a nice error message when something is wrong.
        bound_args = signature.bind(*args, **kwargs)
        bound_args.apply_defaults()
        return bound_args

    def argument_parser(self, command_name):
        """Returns an ArgumentParser matching the signature of command.

        Defaults are not specified in the parser spec because they are applied via the signature
        binding.
        """
        spec = self.command_specs[command_name]
        parser = argparse.ArgumentParser(
            prog=f'clr {self.key}:{command_name}',
            description=spec.docstr,
            add_help=False,
            formatter_class=argparse.RawDescriptionHelpFormatter)

        # Add arguemnt(s) to the parser for each param in the cmd signature.
        for param in spec.signature.parameters.values():
            positional = param.default == Signature.empty

            if positional:
                if param.kind in (param.POSITIONAL_ONLY, param.POSITIONAL_OR_KEYWORD):
                    # Standard positional param without a default. Allow to be added as a positional
                    # OR named arg. One must be specified.
                    group = parser.add_mutually_exclusive_group(required=True)
                    group.add_argument(f'--{param.name}', type=str,
                        help=f'Required. Can also be specified with positional arg {param.name}.')
                    group.add_argument(param.name, nargs='?', type=str,
                        help=f'Required. Can also be specified with --{param.name}.')
                elif param.kind == param.VAR_POSITIONAL:
                    # Vararg (*args) param. There will only ever be one of these
                    # it will be at the end of the positional args.
                    parser.add_argument(param.name, type=str, nargs='*')
                else:
                    raise AssertionError(f'Unexpected kind of positional param {param.name} in '
                                         f'{command_name}: {repr(param.kind)}')
            else:
                # Args with defaults can be refered to by name and are optional.

                # No support for kwargs.
                if param.kind not in (param.POSITIONAL_OR_KEYWORD, param.KEYWORD_ONLY):
                    raise AssertionError(f'Unexpected kwarg **{param.name} in {command_name}.')

                # Assume string type for most args.
                default_type = str
                if param.default is not None:
                    default_type = type(param.default)
                if default_type not in (str, bool, int, float):
                    raise AssertionError(f'Unexpected arg type for {param.name} in {command_name}: '
                                         f'{default_type}')

                # Put the default in the help text to clarify behavior when it is not specified.
                help_text = f"Optional. Defaults to {param.name}='{param.default}'."

                if default_type == bool:
                    # Add both the --arg and --noarg options, but make them mutally exclusive.
                    group = parser.add_mutually_exclusive_group()
                    group.add_argument(f'--{param.name}', action='store_true', help=help_text)
                    group.add_argument(f'--no{param.name}', dest=param.name, action='store_false',
                        help=help_text)
                else:
                    # Add both as optional (nargs=?) positional and named (--arg) for flexibility.
                    # Mutually exclusive and have the same dest.
                    group = parser.add_mutually_exclusive_group()
                    group.add_argument(param.name, nargs='?', type=default_type,
                        help=f'{help_text} Can also be specified with --{param.name}.')
                    group.add_argument(f'--{param.name}', type=default_type,
                        help=f'{help_text} Can also be specified with positional arg {param.name}.')
        return parser


@dataclass
class ErrorLoadingNamespace:
    """Psuedo namespace for when one can't be loaded to show the error message in `clr help`."""
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
        return (f"Error importing module '{NAMESPACE_MODULE_PATHS[self.key]}' for namespace "
                f"'{self.key}':\n\n{self.error}")

@dataclass(frozen=True)
class NamespaceCacheEntry:
    """Picke-able subset of Namespace for NamespaceCache."""
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
NamespaceCacheEntry.argument_parser = Namespace.argument_parser

class NamespaceCache:
    """Cache introspection on command names and signatures to disk.

    This allows subsequent calls to `clr help` or `clr completion_*` to be fast.
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

    def cmd_completion_command(self, query=''):
        """Completion results for first arg to clr."""

        results = []
        if ':' not in query:
            # Suffix system commands with a space.
            results.extend(f'{c} ' for c in self.cache.get('system').commands)
            # Suffix namespaces with a :.
            results.extend(f'{k}:' for k in NAMESPACE_KEYS)
        else:
            namespace_key, _ = query.split(':', 1)
            namespace = self.cache.get(namespace_key)
            results.extend(f'{namespace_key}:{c} ' for c in namespace.commands)

        print('\n'.join(r for r in results if r.startswith(query)), end='')

    def cmd_completion_arg(self, command_name, partial='', bools_only=False):
        """Completion results for arguments.

        Optionally only prints out the boolean flags."""

        namespace_key, command_name = resolve_command(command_name, cache=self.cache)
        namespace = self.cache.get(namespace_key)
        parser = namespace.argument_parser(command_name)
        # argparse doesn't officially support any introspection. Reach into the
        # guts and pull out the bits we need. This isn't perfect, but their
        # internal api has been stable for years and the worst thing that can
        # break is shell completion. Existing off the shelf solutions like the
        # argcomplete package work by monkey-patching argparse before you build
        # your parsers which is potentially even more brittle.

        options = []
        for action in parser._actions:
            if bools_only and not isinstance(action, argparse._StoreConstAction):
                continue
            options.extend(action.option_strings)

        # partial is prepended with a space to stop argparse from parsing it
        partial = partial.strip()
        print('\n'.join(f'{o} ' for o in options if o.startswith(partial)), end='')

    def cmd_argtest(self, a, b, c=4, d=None, e=False):
        """For testing arg parsing."""
        print(f'a={a} b={b} c={c} d={d} e={e}')

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
        provides help for commands.

        $ clr help
        Prints all a short description of all namespaces.

        $ clr namespace
        Prints help for all commands in a namescape.

        $ clr namespace:command
        $ clr namescape command
        Prints help for a command.
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
            self.cache.get(namespace).argument_parser(command).print_help()
        except BrokenPipeError:
            # Less noisy if help is piped to `head`, etc.
            pass
