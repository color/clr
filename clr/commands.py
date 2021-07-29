from importlib import import_module

from enum import Enum
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
import shutil
import argparse
from itertools import takewhile
import traceback

import clr.config

NAMESPACE_MODULE_PATHS = clr.config.read_namespaces()
# Sorted list of command namespace keys.
NAMESPACE_KEYS = sorted({"system", *NAMESPACE_MODULE_PATHS.keys()})

# Load lazily namespace modules as needed. Some have expensive/occasionally
# failing initialization.
__NAMESPACES = {}


def _load_namespace(key):
    """Imports a namespace module."""
    if key == "system":
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
    longdescr = inspect.getdoc(instance) or getattr(instance, "longdescr", descr)
    command_callables = {
        method_name[4:]: method
        for method_name, method in inspect.getmembers(instance, inspect.ismethod)
        if method_name.startswith("cmd_")
    }
    # Build CommandSpecs for each command. These contain metadata about the
    # command and its args. These are kept in a seperate dataclass from the
    # callables because CommandSpec's are pickle-able and cached to disk.
    command_specs = {}
    for command_name, command_callable in command_callables.items():
        docstr = inspect.getdoc(command_callable)
        if docstr is None:
            docstr = ""
        command_specs[command_name] = CommandSpec(
            docstr, Signature.from_callable(command_callable)
        )

    return Namespace(
        key=key,
        descr=descr,
        longdescr=longdescr,
        command_specs=command_specs,
        command_callables=command_callables,
        instance=instance,
    )


def get_namespace(namespace_key):
    """Lazily load and return a namespace"""
    global __NAMESPACES
    if namespace_key not in __NAMESPACES:
        __NAMESPACES[namespace_key] = _load_namespace(namespace_key)
    return __NAMESPACES[namespace_key]


def _get_close_matches(query, options):
    """Utility function for making suggests when `resolve_command` can't resolve a namespace/command
    name."""
    matches = difflib.get_close_matches(query, options, cutoff=0.4)
    if query:
        matches.extend(
            sorted(o for o in options if o.startswith(query) and o not in matches)
        )
    return matches


def resolve_command(query, cache=None):
    """Resolve the string `query' into a (namespace_key, command_name) tuple."""

    if ":" in query:
        namespace_key, command_name = query.split(":", 1)
    else:
        if query in get_namespace("system").commands:
            # System commands can be referred to w/o a namespace so that `clr help` works as
            # expected.
            namespace_key = "system"
            command_name = query
        else:
            # This will still fail, but the error messages will be sensible.
            namespace_key = query
            command_name = ""

    if namespace_key not in NAMESPACE_KEYS:
        print(
            f"Error! Command namespace '{namespace_key}' does not exist.\n"
            f"Closest matches: {_get_close_matches(namespace_key, NAMESPACE_KEYS)}\n\n"
            f"Available namespaces: {NAMESPACE_KEYS}",
            file=sys.stderr,
        )
        sys.exit(1)

    namespace = cache.get(namespace_key) if cache else get_namespace(namespace_key)
    if command_name not in namespace.commands:
        print(
            f"Error! Command '{command_name}' does not exist in namespace '{namespace_key}' - "
            f"{namespace.descr}.\nClosest matches: "
            f"{_get_close_matches(command_name, namespace.commands)}\n\nAvailable commands: "
            f"{namespace.commands}\nSee `clr help {namespace_key}` for details.",
            file=sys.stderr,
        )
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


@dataclass(frozen=True)
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
        parameters = signature.parameters.values()
        has_var_positional = any(p.kind == p.VAR_POSITIONAL for p in parameters)

        # Parse the command line arguments, starting after command name.
        parsed = NoneIgnoringArgparseDestination()
        self.argument_parser(command_name).parse_args(argv, namespace=parsed)

        # Turn parsed args into something we can pass to signature.bind.
        args = []
        kwargs = {}

        # Track whether the current param is before a VAR_POSITIONAL param.
        before_var_positional = has_var_positional

        for param in parameters:
            if param.kind == param.VAR_POSITIONAL:
                args.extend(getattr(parsed, param.name))
                before_var_positional = False
            elif before_var_positional:
                args.append(getattr(parsed, param.name))
            elif hasattr(parsed, param.name):
                # BoundArguments will apply the defaults.
                kwargs[param.name] = getattr(parsed, param.name)

        # Ensure the signature is valid and applies default. Could use argparse to do more of this,
        # but adds correctness guarantees and gives a nice error message when something is wrong.
        bound_args = signature.bind(*args, **kwargs)
        bound_args.apply_defaults()
        return bound_args

    def argument_parser(self, command_name):
        """Returns an ArgumentParser matching the signature of command.

        Defaults are not specified in the parser spec because they are applied via the signature
        binding.

        General approach is to allow as much flexibility for how arguements are specificied as
        possible while maintaining 100% compatibility with legacy arg parsing (if it used to work it
        should continue to work). The original approach had a stricter seperation between positional
        and named arguements- optional arguements could still be given positionally, but required
        ones had to be positional. The new approach is compatible with old incantations, but also
        allows all arguments to be specified with named flags (--arg ARG). Just like in calling
        methods in code, using all positional arguments is more concise, but when dealing with more
        than a few it can become less clear what is going on. Additionally using named flags is more
        discoverable when using shell completion.

        - Arguments are considered required if they don't have a default value.
        - Required arguments can be specified either positionally or named. Exactly one usage must
          be present.
        - If the n-th positional argument is specified with a named flag, all subsequent ones must
          as well.
        - Varargs (*arg) parameters are a special case, must be used positionally, and can be be
          empty list.
        - Optional (has a default) parameters can also be specified either way, however can also be
          left out.
        - All arguments are assumed to be strings unless they specify a default with another type.
          Only str, bool, int and float are supported. If a default of that type is specified,
          arguments are cast to that type before calling.
        - Boolean parameters (to be boolean means they specify a default so they are also optional)
          get special handling and both --arg and --noarg flags that don't take a value are make
          avaliable.
        - If there is a vararg, required args can only be specified positionally and optional args
          can not be specified positionall.y

        Taking the system:argtest command as an example:
        def cmd_argtest(self, a, b, c=4, d=None, e=False)

        These are valid usages:
        clr argtest 1 2
        clr argtest 1 --b 2
        clr argtest 1 --b=2
        clr argtest 1 2 3
        clr argtest 1 2 3 4
        clr argtest 1 2 --e
        clr argtest --a=1 --b=2
        clr argtest --a=1 --b=2 --e
        clr argtest --a=1 --b=2 --noe
        clr argtest --e --d=6 --a=1 --b=2
        clr argtest --a=1 --b=2 --c=3 --d=4 --e

        These are invalid usages:
        clr argtest 1 --a=2 (a specified twice, b missing)
        clr argtest 1 2 --a=3 (a specified twice)
        clr argtest 1 2 --e --noe (e and noe are mutually exclusive)
        clr argtest 1 2 --c=a (c must be an int)
        """
        spec = self.command_specs[command_name]
        parameters = spec.signature.parameters.values()
        parser = argparse.ArgumentParser(
            prog=f"clr {self.key}:{command_name}",
            description=spec.docstr,
            add_help=False,
            formatter_class=argparse.RawDescriptionHelpFormatter,
        )

        # Track whether there is a var positional/vararg/*args parameter. If so, less flexibility on
        # positional vs named.
        has_var_positional = any(p.kind == p.VAR_POSITIONAL for p in parameters)
        # We are before a var_positional if there is a var_positional.
        before_var_positional = has_var_positional

        # Add argument(s) to the parser for each param in the cmd signature.
        for param in parameters:
            name = param.name
            required = param.default == Signature.empty

            if before_var_positional and param.kind == param.VAR_POSITIONAL:
                before_var_positional = False
            if before_var_positional and not required:
                raise AssertionError(
                    f"Can not have optional arg ({param}) before a *vararg in {self.key}.cmd_{command_name}"
                )

            # When None will assume str type.
            arg_type = None

            # Special support for Enum values.
            if issubclass(param.annotation, Enum):
                def enum_parser(arg):
                    arg = arg.upper()
                    assert arg in param.annotation.__members__, f"Arg ({name}) must be one of {[v.name for v in param.annotation]}."
                    return param.annotation.__members__[arg]
                arg_type = enum_parser

            if required:
                if param.kind in (param.POSITIONAL_ONLY, param.POSITIONAL_OR_KEYWORD):
                    if has_var_positional:
                        parser.add_argument(name, type=str, help=f"Required.")
                    else:
                        # Standard positional param without a default. Allow to be added as a positional
                        # OR named arg. One must be specified.
                        group = parser.add_mutually_exclusive_group(required=True)
                        group.add_argument(
                            f"--{name}",
                            type=arg_type,
                            help=f"Required. Can also be specified with positional arg {name}.",
                        )
                        group.add_argument(
                            name,
                            nargs="?",
                            type=arg_type,
                            help=f"Required. Can also be specified with --{name}.",
                        )
                elif param.kind == param.VAR_POSITIONAL:
                    # Vararg (*args) param. There will only ever be one of these
                    # it will be at the end of the positional args.
                    if self.key == "system" and command_name == "smart_complete":
                        # Special case to support smart completions.
                        nargs = argparse.REMAINDER
                    else:
                        nargs = "*"
                    parser.add_argument(name, type=str, nargs=nargs)
                else:
                    raise AssertionError(
                        f"Unexpected kind of positional param {name} in "
                        f"{command_name}: {repr(param.kind)}"
                    )
            else:
                # Args with defaults can be refered to by name and are optional.

                # No support for kwargs.
                if param.kind not in (param.POSITIONAL_OR_KEYWORD, param.KEYWORD_ONLY):
                    raise AssertionError(
                        f"Unexpected kwarg **{name} in {command_name}."
                    )

                if not arg_type and param.default is not None:
                    # Infer from type of default
                    arg_type = type(param.default)
                    if arg_type not in (str, bool, int, float):
                        raise AssertionError(
                            f"Unexpected arg type for {name} in {command_name}: "
                            f"{arg_type}"
                        )

                # Put the default in the help text to clarify behavior when it is not specified.
                default_text = str(param.default)
                if isinstance(param.default, Enum):
                    default_text = param.default.name.lower()
                help_text = f"Optional. Defaults to {name}='{default_text}'."

                if arg_type == bool:
                    # Add both the --arg and --noarg options, but make them mutally exclusive.
                    group = parser.add_mutually_exclusive_group()
                    group.add_argument(
                        f"--{name}",
                        action="store_true",
                        default=None,
                        help=f"{help_text} Inverse of --no{name}.",
                    )
                    group.add_argument(
                        f"--no{name}",
                        dest=name,
                        action="store_false",
                        default=None,
                        help=f"{help_text} Inverse of --{name}.",
                    )
                else:
                    if has_var_positional:
                        parser.add_argument(
                            f"--{name}", type=arg_type, help=help_text
                        )
                    else:
                        # Add both as optional (nargs=?) positional and named (--arg) for
                        # flexibility. Mutually exclusive and have the same dest.
                        group = parser.add_mutually_exclusive_group()
                        group.add_argument(
                            name,
                            nargs="?",
                            type=arg_type,
                            help=f"{help_text} Can also be specified with --{name}.",
                        )
                        group.add_argument(
                            f"--{name}",
                            type=arg_type,
                            help=f"{help_text} Can also be specified with positional arg {name}.",
                        )
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
        tb = ''.join(traceback.TracebackException.from_exception(self.error).format())
        return (
            f"Error importing module '{NAMESPACE_MODULE_PATHS[self.key]}' for namespace "
            f"'{self.key}':\n\n{type(self.error).__name__} {self.error}\n{tb}"
        )


@dataclass(frozen=True)
class NamespaceCacheEntry:
    """Picke-able subset of Namespace for NamespaceCache."""

    key: str
    descr: str
    longdescr: str
    command_specs: dict

    @staticmethod
    def create(namespace):
        return NamespaceCacheEntry(
            namespace.key, namespace.descr, namespace.longdescr, namespace.command_specs
        )


# Steal some functionality.
NamespaceCacheEntry.commands = Namespace.commands
NamespaceCacheEntry.argument_parser = Namespace.argument_parser


class NamespaceCache:
    """Cache introspection on command names and signatures to disk.

    This allows subsequent calls to `clr help` or `clr completion_*` to be fast.
    Necessary to work around the fact that many clr command namespace modules
    import the world and initialize state on import. The cache is used only for
    help and completion calls, when actually calling a clr command its spec is
    always loaded from the module.
    """

    def __init__(self):
        # Place the cache file in the temp dir with a static file name. Data stored in
        # this file is easily regeneratable in the event of a system restart, but should
        # be left behind after the process is complete for subsequent clr calls to find.
        tmpdir = os.environ.get("TMPDIR", "/tmp")
        self.cache_fn = os.path.join(tmpdir, "clr_command_cache")
        # Lazily load the cache file so that clr calls that don't need to won't hit the
        # disk.
        self.cache = None

    def get(self, namespace_key):
        # Don't cache the system namespace. It is already loaded.
        if namespace_key == "system":
            return get_namespace("system")
        # Return from cache if present.
        self._load_cache_if_needed()
        if namespace_key in self.cache:
            return self.cache[namespace_key]
        return self._load_and_sync_entry(namespace_key)

    def clear(self):
        # Create a new empty db.
        with shelve.open(self.cache_fn, flag="n"):
            pass

    def _load_cache_if_needed(self):
        if self.cache is not None:
            # Already loaded.
            return
        try:
            # Cache is stored on disk as a shelve, but loaded into memory and then
            # closed right away so that multiple processes are unlikely to conflict
            # trying to access it.
            with shelve.open(self.cache_fn) as cache_shelve:
                self.cache = dict(cache_shelve)
        except Exception:
            # Caching is considered best effort and fails silently. Can always load the
            # module, this is just slower.
            self.cache = {}

    def _load_and_sync_entry(self, namespace_key):
        namespace = get_namespace(namespace_key)
        if isinstance(namespace, ErrorLoadingNamespace):
            # Don't cache errors.
            return namespace

        entry = NamespaceCacheEntry.create(namespace)
        self.cache[namespace_key] = entry

        # Try to save the entry to disk. Fail silently.
        try:
            with shelve.open(self.cache_fn) as cache_shelve:
                cache_shelve[namespace_key] = entry
        except Exception:
            pass

        return entry


class System:
    """Namespace for system commands in the clr tool.

    Commands defined here will be avaliable directly without specifying a
    namespace. For example `clr help` instead of `clr system:help`. Be careful
    not to define commands here that have the same name as a defined namespace
    or it may be obscured."""

    descr = "clr built-in commands"

    cache = NamespaceCache()

    def cmd_clear_cache(self):
        """Clear clr's cache.

        clr caches command specs to disk to speed up help and completions.
        Run this to clear the cache if your results are stale."""
        self.cache.clear()

    def cmd_complete_command(self, query=""):
        """Completion results for first arg to clr."""

        results = []
        if ":" not in query:
            # Suffix system commands with a space.
            results.extend(f"{c} " for c in self.cache.get("system").commands)
            # Suffix namespaces with a :.
            results.extend(f"{k}:" for k in NAMESPACE_KEYS)
        else:
            namespace_key, _ = query.split(":", 1)
            namespace = self.cache.get(namespace_key)
            results.extend(f"{namespace_key}:{c} " for c in namespace.commands)
        print_for_complete(query, results, add_space=False)

    def cmd_complete_arg(self, command_name, partial="", bools_only=False):
        """Completion results for arguments.

        Optionally only prints out the boolean flags."""

        namespace_key, command_name = resolve_command(command_name, cache=self.cache)
        namespace = self.cache.get(namespace_key)

        options = []
        for param in namespace.command_specs[
            command_name
        ].signature.parameters.values():
            is_bool = type(param.default) == bool
            if not bools_only or is_bool:
                options.append(f"--{param.name}")
            if is_bool:
                options.append(f"--no{param.name}")
        # partial is prepended with a space to stop argparse from parsing it
        partial = partial.strip()
        print_for_complete(partial, results)

    def cmd_smart_complete(self, *existing_args):
        """Smart/opinionated completion.

        Only completes the next missing required arg if there are any. Afterward
        suggests optional args."""

        if len(existing_args) < 2:
            # Invalid call.
            return

        command_name = existing_args[1]
        existing_args = existing_args[2:]

        # existing_args will contain at least an empty str element if we're past the command name.
        if not existing_args:
            self.cmd_complete_command(query=command_name)
            return

        # Special case for the first/only arg to help.
        if command_name in ("system:help", "help") and len(existing_args) < 2:
            self.cmd_complete_command(query=existing_args[0])
            return

        current_arg = existing_args[-1]
        previous_args = existing_args[:-1]

        def is_positional(arg):
            return not arg.startswith("--")

        existing_positional_args = len(list(takewhile(is_positional, previous_args)))

        namespace_key, command_name = resolve_command(command_name, cache=self.cache)
        parameters = (
            self.cache.get(namespace_key)
            .command_specs[command_name]
            .signature.parameters.values()
        )

        # Scan over all parameters for the command to build up data for the following purposes:
        # Will suggest the first missing required arg if there is one.
        missing_required_args = []
        # Once all the required args are present, will suggest the optional ones.
        missing_optional_args = []
        # Boolean args don't need to be followed by an value.
        boolean_options = set()
        # No filename completion for numberical args.
        numerical_options = set()
        # Mapping from enum options to their class,
        enum_options = {}
        # Required args don't have named flags if there is a var positional.
        has_var_positional = False
        for param_index, param in enumerate(parameters):
            if param.kind == param.VAR_POSITIONAL:
                has_var_positional = True
                continue

            required = param.default == Signature.empty
            missing_args = missing_required_args if required else missing_optional_args
            arg_names = [f"--{param.name}"]

            if type(param.default) == bool:
                arg_names.append(f"--no{param.name}")
                boolean_options.update(arg_names)
            elif type(param.default) in (int, float):
                numerical_options.update(arg_names)
            elif issubclass(param.annotation, Enum):
                enum_options[arg_names[0]] = param.annotation

            present_positionally = existing_positional_args > param_index
            present_named = any(a in previous_args for a in arg_names)
            if not present_positionally and not present_named:
                missing_args.extend(arg_names)

        # If the previous argument is a flag that expects a value argument.
        if (
            previous_args
            and not is_positional(previous_args[-1])
            and previous_args[-1] not in boolean_options
        ):
            if previous_args[-1] in numerical_options:
                # No completion.
                return
            if previous_args[-1] in enum_options:
                # Suggest all enum values.
                for value in enum_options[previous_args[-1]]:
                    if value.name.startswith(current_arg.upper()):
                        print(f'{value.name.lower()} ')
                return
            # Return with exit code 2 to indicate to the shell that standard
            # file/dir completion is desired.
            return 2

        # Suggest all missing optional args.
        print_for_complete(current_arg, missing_optional_args)

        if missing_required_args:
            if has_var_positional:
                # When there is a var positional arg, required args must be specified positionally.
                if not current_arg:
                    print(
                        f"\nMust give positional arg for {missing_required_args[0]}",
                        file=sys.stderr,
                    )
                return 2
            else:
                # Required arg not present. Suggest that only.
                print(f"{missing_required_args[0]} ", end="")
                return


        # Standard file/dir completion for *arg.
        if has_var_positional:
            return 2

    def cmd_profile_imports(self, *namespaces):
        """Prints some debugging information about how long it takes to import clr namespaces."""
        if not namespaces:
            namespaces = NAMESPACE_KEYS
        results = {}
        for index, key in enumerate(namespaces):
            start_time = time.time()
            get_namespace(key)
            results[f"#{index + 1}-{key}"] = time.time() - start_time

        print(
            "\n".join(
                f"{k}: {int(1000*v)}"
                for k, v in sorted(results.items(), key=lambda i: i[1])
            )
        )

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
            print("Available namespaces")
            for namespace_key in NAMESPACE_KEYS:
                print(
                    " ",
                    namespace_key.ljust(20),
                    "-",
                    self.cache.get(namespace_key).descr,
                )
            return

        # If they passed just one arg and it is a namespace key, print help for the full namespace.
        if query.endswith(":"):
            query = query[:-1]
        if query in NAMESPACE_KEYS and not query2:
            namespace = self.cache.get(query)
            print(f"{query} - {namespace.longdescr}\n")
            for command in namespace.commands:
                print(f"  clr {query}:{command}")
            for command in namespace.commands:
                print("-" * 80)
                self.print_help_for_command(query, command)
            return

        if query2:
            query = f"{query}:{query2}"
        namespace_key, command_name = resolve_command(query, cache=self.cache)
        self.print_help_for_command(namespace_key, command_name)

    def print_help_for_command(self, namespace, command):
        try:
            self.cache.get(namespace).argument_parser(command).print_help()
        except BrokenPipeError:
            # Less noisy if help is piped to `head`, etc.
            pass

    def cmd_argtest(self, a, b, c=4, d=None, e=False, f=True):
        """For testing arg parsing."""
        print(f"a={a} b={b} c={c} d={d} e={e} f={f}")

    def cmd_argtest2(self, a, b, *c, d=4, e=None, f=False, g=""):
        """For testing arg parsing."""
        print(f"a={a} b={b} c={c} d={d} e={e} f={f} g={g}")


def print_for_complete(current, options, add_space=True):
    options = [o for o in options if o.startswith(current)]
    if not options:
        return
    if add_space:
        options = [f"{o} " for o in options]
    print("\n".join(options), end="")
