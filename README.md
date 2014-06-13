# clr

A command line tool for executing custom python scripts.

## Getting Started

* Install clr
```
$ pip install git+https://git+https://github.com/ColorGenomics/clr.git@v0.1.0
```

* Create clrfile.py in your root directory
```
# clrfile.py
commands = {
  'deploy': 'clr_commands.deploy',
  'vcf':    'clr_commands.vcf',
}
```

* Run your command
```
$ clr deploy:release web_server
```
