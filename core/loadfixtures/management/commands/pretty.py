import subprocess

import pylibcheck
from django.core.management import BaseCommand


class Command(BaseCommand):
    help = "Makes files pretty using isort and black formatter."
    packages = ["black", "isort"]

    def add_arguments(self, parser):
        parser.add_argument("path", nargs="+", help="File/Paths to format.")
        parser.add_argument(
            "-l", dest="line-length", default="88", help="No of characters per line."
        )
        parser.add_argument(
            "-t", dest="target-version", default="py310", help="Python version."
        )

    def handle(self, *args, **options):
        options["flags"] = [
            "-t" + options["target-version"],
            "-l " + options["line-length"],
        ]
        if not pylibcheck.checkPackage("black"):
            raise Exception('Package "black" not found, install using pip.')
        if not pylibcheck.checkPackage("isort"):
            raise Exception(
                'Package "isort" not found. Either install using pip or set -i flag for autoinstall.'
            )

        try:
            cmd = ["isort", *options["path"]]
            output = subprocess.check_output(["isort", *options["path"]])
        except subprocess.CalledProcessError as e:
            raise Exception(output)

        try:
            cmd = ["black", *options["flags"], *options["path"]]
            subprocess.check_output(["black", *options["flags"], *options["path"]])
        except subprocess.CalledProcessError as e:
            raise Exception(e)
