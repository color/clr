from setuptools import setup
from pathlib import Path
import re

requirements = ["dataclasses;python_version<'3.7'", "honeycomb-beeline"]

version = re.findall('__version__ = "(.+)"', Path("clr/_version.py").read_text())[0]
install_requirements=Path("requirements.txt").read_text().splitlines()


setup(
    name="clr",
    version=version,
    description="A command line tool for executing custom python scripts.",
    author="Color",
    author_email="dev@getcolor.com",
    url="https://github.com/color/clr",
    packages=["clr"],
    entry_points={
        "console_scripts": ["clr = clr:main"],
    },
    install_requires=install_requirements,
    license="MIT",
    include_package_data=True,
    package_data={
        "": ["completion.*"],
    },
)
