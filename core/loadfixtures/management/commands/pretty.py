import subprocess

import pylibcheck
from django.core.management import BaseCommand


class Command(BaseCommand):
    help = "Makes files pretty using isort and black formatter."
    packages = ["black", "isort"]

    def add_arguments(self, parser):
        parser.add_argument("path", nargs="+", help="File/Paths to format.")
        parser.add_argument(
            "-l",
            dest="line-length",
            default="80",
            help="No of characters per line.",
        )
        parser.add_argument(
            "-t", dest="target-version", default="py310", help="Python version."
        )

    def handle(self, *args, **options):
        options["flags"] = [
            "-t" + options["target-version"],
            "-l " + options["line-length"],
        ]

        for package in self.packages:
            if not pylibcheck.checkPackage(package):
                raise Exception('Package "{}" not found, install using pip.'.format(package))

        try:
            cmd = ["isort", *options["path"]]
            subprocess.check_output(cmd)
        except subprocess.CalledProcessError as e:
            raise Exception(e)

        try:
            cmd = ["black", *options["flags"], *options["path"]]
            subprocess.check_output(cmd)
        except subprocess.CalledProcessError as e:
            raise Exception(e)
