from past.builtins import execfile
import os.path


def find_clrfile(name='clrfile.py'):
    path = '.'
    searched = []
    while os.path.split(os.path.abspath(path))[1]:
        file_path = os.path.abspath(os.path.join(path, name))
        searched.append(file_path)
        if os.path.exists(file_path):
            return file_path
        path = os.path.join('..', path)
    raise Exception("%s could not be located. Searched in %s" % (name, searched))

def commands():
    config = _get_config()
    return config['commands']

def options():
    config = _get_config()
    return config['options']

_config_cache = {}
def _get_config():
    if not _config_cache:
        execfile(find_clrfile(), _config_cache)
    return _config_cache
