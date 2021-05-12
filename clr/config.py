"""The clr tool is configred using a python source file (clrfile.py) that is
distributed externally to this tool. On start up we scan for this file and
import it to initialize the command list
"""

from pathlib import Path
import os.path
import os
import sys
import runpy

NAME = 'clrfile.py'

def find_clrfile():
    """Scan for `clrfile.py` defining clr command namespaces.

    Searches from cwd and then up the tree. Also looks in $COLOR_ROOT if set.

    TODO(michael.cusack): Should we allow multiple results and import from them
    all? This would allow clr commands to be defined heirarchically? More
    flexible but harder to reason about.
    """
    search_paths = []
    search_paths.extend(Path(os.getcwd()).parents)
    if 'COLOR_ROOT' in os.environ:
        search_paths.append(Path(os.environ['COLOR_ROOT']))

    for search_path in search_paths:
        file_path = search_path / NAME
        if file_path.exists():
            return file_path

    print(f"WARNING: {NAME} could not be located. Only the `system` namespace will be avaliable."
        f" Searched in {', '.join(str(p) for p in search_paths)}", file=sys.stderr)

def read_namespaces():
    """Returns a mapping from namespace keys to python module paths.

    find_clrfile() returns a filesystem path. It may not be in the PYTHONPATH.
    Use runpy to "import" the clrfile into a isolated namespace and extract the
    'commands'. The values of this mapping are python module names that *are* on
    the PYTHONPATH and can be imported with importlib.import_module.
    """
    clrfile = find_clrfile()
    if not clrfile:
        return {}
    return runpy.run_path(clrfile)['commands']
