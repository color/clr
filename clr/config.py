import os.path


def find_clrfile(name='clrfile.py'):
    path = '.'
    while os.path.split(os.path.abspath(path))[1]:
        file_path = os.path.join(path, name)
        if os.path.exists(file_path):
            return os.path.abspath(file_path)
        path = os.path.join('..', path)
    raise Exception("clrfile.py could not be located.")

config = {}
exec(find_clrfile(), config)
