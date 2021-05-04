from past.builtins import execfile
from pathlib import Path
import os.path
import os
import runpy

def find_clrfile(name='clrfile.py'):
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
        file_path = search_path / name
        if file_path.exists():
            return file_path
    raise Exception("%s could not be located. Searched in %s" % (name, search_paths))

def read_namespaces():
    return runpy.run_path(find_clrfile())['commands']
