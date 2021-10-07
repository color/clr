# clr

A command line tool for executing custom python scripts.

## Getting Started

* Install clr
```
$ pip install git+https://github.com/color/clr.git@v0.2.0
```

* Create a custom command
```
# color/src/clr_commands/say.py
class Commands(object):
    descr = "say commands"

    def cmd_hello_world(self):
        print "hello world!"

COMMANDS = Commands()
```

* Create clrfile.py in your root directory
```
# color/clrfile.py
commands = {
  'say': 'clr_commands.say',
}
```

* Run your command
```
$ clr say:hello_world
> hello world!
```

## Useful commands
* Get available namespaces
```
$ clr help
```

* Get available commands in a namespace
```
$ clr help namespace
```

## Development
* Create a virtualenv and activate it
```
python3 -m venv <location>
source <location>/bin/activate
```
* Install this package as editable (symlinked to source files)
```
pip install -e .
```
* Run the tests
```
COLOR_ENV=tests/env.yaml python setup.py test
```
