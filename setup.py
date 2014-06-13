import os

from clr import __version__

try:
  from setuptools import setup
except:
  from distutils.core import setup


platform_packages = {
    'Darwin': ['readline'],
}.get(os.uname()[0], [])

setup(name = "clr",
      version = __version__,
      description = "A command line tool for executing custom python scripts.",
      author = "Color Genomics",
      author_email = "dev@getcolor.com",
      url = "https://github.com/ColorGenomics/clr",
      entry_points = {
        'console_scripts': [ 'clr = clr:main' ],
      },
      install_requires = [] + platform_packages,
      )
