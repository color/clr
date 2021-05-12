from setuptools import setup

setup(name = "clr",
      version = "0.2.0",
      description = "A command line tool for executing custom python scripts.",
      author = "Color",
      author_email = "dev@getcolor.com",
      url = "https://github.com/color/clr",
      packages = ["clr"],
      entry_points = {
        "console_scripts": [ "clr = clr:main" ],
      },
      install_requires=[
        "dataclasses"
      ],
      setup_requires=['pytest-runner'],
      tests_require=['pytest'],
      license = "MIT",
      include_package_data=True,
      package_data={
        "": ["completion.*"],
      }
)
