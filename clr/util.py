import imp


def path_of_module(mod, path=None):
    a, b = peel(mod, '.')
    _, path, _ = imp.find_module(a, path)

    if b:
        return path_of_module(b, [path])
    else:
        return path

def peel(string, delimitter):
    peeled = string.split(delimitter, 1)
    if len(peeled) == 1:
        return peeled[0], ''
    else:
        return peeled[0], peeled[1]
