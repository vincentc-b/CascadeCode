"""Package repository playbooks as resources without maintaining a second copy."""

from setuptools import find_packages, setup

setup(
    packages=find_packages(include=["cascade", "cascade.*"]) + ["cascade._skill_templates"],
    package_dir={"cascade._skill_templates": "skills"},
)
