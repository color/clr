import os
from setuptools import setup


setup(name = "clr",
      version = "0.1.9",
      description = "A command line tool for executing custom python scripts.",
      author = "Color Genomics",
      author_email = "dev@getcolor.com",
      url = "https://github.com/ColorGenomics/clr",
      packages = ["clr"],
      entry_points = {
        "console_scripts": [ "clr = clr:main" ],
      },
      install_requires=[
        "future>=0.16.0",
        "dataclasses"
      ],
      setup_requires=['pytest-runner'],
      tests_require=['pytest'],
      license = "MIT",
)
