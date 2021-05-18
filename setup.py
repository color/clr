from setuptools import setup

requirements = ["dataclasses==0.8;python_version<'3.7'"]

setup(
    name="clr",
    version="0.3.0",
    description="A command line tool for executing custom python scripts.",
    author="Color",
    author_email="dev@getcolor.com",
    url="https://github.com/color/clr",
    packages=["clr"],
    entry_points={"console_scripts": ["clr = clr:main"],},
    install_requires=requirements,
    setup_requires=["pytest-runner"],
    tests_require=requirements + ["pytest==6.2.4"],
    license="MIT",
    include_package_data=True,
    package_data={"": ["completion.*"],},
)
