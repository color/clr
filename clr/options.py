from collections import defaultdict

import clr.config


def get_options():
    return [__import__(o, {}, {}, ['']).OPTIONS for o in clr.config.options()]

def add_global_options(parser):
    for o in get_options():
        o.add_options(parser)

def handle_global_options(opts):
    hooks = defaultdict(lambda: [])

    for o in get_options():
        for hook, fun in (o.handle_options(opts) or {}).items():
            hooks[hook].append(fun)

    return hooks
