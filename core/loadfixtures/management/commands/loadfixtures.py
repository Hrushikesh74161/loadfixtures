__author__ = 'G. Hrushikesh Reddy <hrushi74161@gmail.com>'
import os
import re
from collections import defaultdict

from django.apps import apps
from django.conf import settings
from django.core.management import BaseCommand, call_command
from django.db import router
from django.utils.module_loading import import_string


class Command(BaseCommand):
    help = "Upgrade to loaddata command."

    def add_arguments(self, parser):
        parser.add_argument(
            "--fixture",
            "-f",
            action="append",
            default=[],
            dest="fixtures",
            help="Fixture labels to load.",
        )
        parser.add_argument(
            "--database",
            default=None,
            help=(
                "Nominates a specific database to load fixtures into. Defaults to the "
                '"default" database or according to your routing.'
            ),
        )
        parser.add_argument(
            "--app",
            "-a",
            action="append",
            default=[],
            dest="app_labels",
            help="Load fixtures from specified app(s).",
        )
        parser.add_argument(
            "--ignorenonexistent",
            "-i",
            action="store_true",
            dest="ignore",
            help="Ignores entries in the serialized data for fields that do not "
            "currently exist on the model.",
        )
        parser.add_argument(
            "-e",
            "--exclude",
            action="append",
            default=[],
            help=(
                "An app_label or app_label.ModelName to exclude. Can be used multiple "
                "times."
            ),
        )
        parser.add_argument(
            "--format",
            help="Format of serialized data when reading from stdin.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help = "Outputs which fixtures are going to be loaded, without loading them."
        )

    def setup_fields(self):
        onetooneormany = set(settings.LOAD_FIXTURES["ONETOONEORMANY"])
        onetooneormany.update(
            ["django.db.models.ForeignKey", "django.db.models.OneToOneField"]
        )
        self.onetooneormany = set()

        for field in onetooneormany:
            self.onetooneormany.add(import_string(field))

    def make_model_info(self):
        self.models = defaultdict(dict)
        for app, models in apps.all_models.items():
            for model_name, model_class in models.items():
                self.models[model_class] = {
                    "fixture_label": model_class._meta.label_lower.replace(
                        ".", "_"
                    ),
                    "model_label": model_class._meta.label,
                    "app_label": app,
                }

    def setup(self, options, *args):
        self.exclude = set(options["exclude"])
        self.app_labels = set(options["app_labels"])
        self.fixtures = set(options["fixtures"])
        self.is_dry_run = options["dry_run"]
        del options["app_labels"]
        del options["fixtures"]
        del options["dry_run"]

        self.make_model_info()
        self.setup_fields()

        self.run_pre_build_checks()
        self.build_graph()
        self.run_post_build_checks()

    def handle(self, *args, **options):
        self.setup(options, *args)
        self.load(*args, **options)

    # topological sorting
    def build_graph(self):
        """
        Builds the relation graph of models.
        """
        # model_label = model._meta.label
        # model_info = {
        #     'fixture_label':,
        #     'model_label':,
        #     'app_label':,
        #     }
        # self.graph = {
        # level : [model_info's]
        # }
        self.graph = defaultdict(list)
        # {fixture_label: level}
        self.lookup_table = dict()

        # puts the model in the specific level it belongs to in self.graph
        # and returns its level
        def build(model, model_info):
            if model_info["fixture_label"] in self.lookup_table:
                return self.lookup_table[model_info["fixture_label"]]

            forward_fields = model._meta._forward_fields_map
            forward_relation_models = set()

            for _, field in forward_fields.items():
                # relations with self are not considered because
                # django's loaddata command, disables constraints
                # while added fixtures, and runs constraint check
                # after loading,
                # also because we are using recursion
                # this will create infinite loop
                if (
                    isinstance(field, tuple(self.onetooneormany))
                    and field.related_model != model
                ):
                    forward_relation_models.add((field.related_model))

            level = 0
            # if no forward relation models then its level is 0
            if forward_relation_models:
                level = 1 + max(
                    build(related_model, self.models[related_model])
                    for related_model in forward_relation_models
                )

            # add curr models level to lookup_table for later usage
            self.lookup_table[model_info["fixture_label"]] = level

            self.add_to_graph(level, model_info)

            return level

        for model, model_info in self.models.items():
            build(model, model_info)

    @property
    def levels(self):
        try:
            levels = max(key for key in self.graph)
        except ValueError:
            self.stdout.write("No fixtures to load.")
            exit()
        else:
            return levels

    def load(self, *args, **options):
        for level in range(self.levels + 1):
            for model_info in self.graph[level]:
                fixtures = self.get_fixtures_and_db(model_info, options)
                if self.is_dry_run:
                    self.dry_run(model_info, fixtures, **options)
                else:
                    self.loaddata(fixtures, *args, **options)

    def get_fixtures_and_db(self, model_info, options):
        fixture_files = self.find_fixtures(model_info)
        if options["database"] is None:
            options["database"] = self.get_db(model_info["model_label"])

        return fixture_files

    def dry_run(self, model_info, fixtures, **options):
        if fixtures:
            self.stdout.write('App: {}'.format(model_info["app_label"]))
            self.stdout.write('Model: {}'.format(model_info['model_label']))
            self.stdout.write('Database: {}'.format(options['database']))
            self.stdout.write('Fixture(s):')
            for fixture in fixtures:
                self.stdout.write(fixture)
            self.stdout.write('\n')

    def loaddata(self, fixtures, *args,**options):
        if fixtures:
            call_command("loaddata", *fixtures, **options)

    def find_fixtures(self, model_info):
        fixture_files = set()

        pattern = r".*\/" + model_info["fixture_label"] + r"\..+"

        dirs_to_search = set(settings.FIXTURE_DIRS)
        app_fixture_path = (
            self.get_app_path(model_info["app_label"]) + "/fixtures"
        )
        dirs_to_search.add(app_fixture_path)

        for dir in dirs_to_search:
            for root, _, files in os.walk(dir):
                for file in files:
                    match_path = root + "/" + file
                    if re.fullmatch(pattern, match_path):
                        fixture_files.add(match_path)

        return fixture_files

    def get_app_path(self, app):
        app_config = apps.get_app_config(app)
        return app_config.path

    def get_db(self, model):
        if type(model) == str:
            model = apps.get_model(model)

        return router.db_for_write(model)

    def run_pre_build_checks(self):
        self.check_apps()
        self.check_fixtures_pre_build()

    def run_post_build_checks(self):
        self.check_fixtures_post_build()

    def check_apps(self):
        for app in self.app_labels:
            # not using apps.is_installed, because
            # app_label is probably different from what it is in INSTALLED_APPS
            # this is the case if app is located in folder where settings file is present
            # this is possible if app is started using django-admin
            # check if app is present in INSTALLED_APPS
            try:
                apps.get_app_config(app)
            except LookupError:
                msg = "App '{}' is either not in INSTALLED_APPS or does not exist.".format(
                    app
                )
                raise Exception(msg)

            # check if app is in both apps to load and apps to exclude
            if app in self.exclude:
                msg = "App '{}' can't be in both apps to load and excluded apps.".format(
                    app
                )
                raise Exception(msg)

    def check_fixtures_post_build(self):
        for fixture in self.fixtures:
            # check if it is in lookup lookup_table
            try:
                self.lookup_table[fixture]
            except KeyError:
                msg = "Fixture '{}' not found. Does not belong to any model.".format(
                    fixture
                )
                raise Exception(msg)

    def check_fixtures_pre_build(self):
        for _, model_info in self.models.items():
            fixture = model_info["fixture_label"]

            if fixture in self.fixtures:
                if fixture in self.exclude:
                    msg = "Fixture '{}' can't be in fixtures to load and in excluded fixtures.".format(
                        fixture
                    )
                    raise Exception(msg)

                if model_info["model_label"] in self.exclude:
                    msg = (
                        "Fixture {}'s model '{}' is in excluded models.".format(
                            fixture, model_info["model_label"]
                        )
                    )
                    raise Exception(msg)

                if model_info["app_label"] in self.exclude:
                    msg = "Fixture {}'s app '{}' is in excluded apps.".format(
                        fixture, model_info["app_label"]
                    )
                    raise Exception(msg)

    def add_to_graph(self, level, model_info):
        # if app or model or fixture is excluded,
        # then those are not added to graph
        if (
            model_info["fixture_label"] in self.exclude
            or model_info["model_label"] in self.exclude
            or model_info["app_label"] in self.exclude
        ):
            return
        # if user explicitly gives fixtures or/and app_labels
        # then only add those to graph
        if self.app_labels or self.fixtures:
            if (
                model_info["app_label"] not in self.app_labels
                and model_info["fixture_label"] not in self.fixtures
            ):
                return

        self.graph[level].append(model_info)

    def pretty_print_graph(self):
        for level, model_infos in self.graph.items():
            print("Level : ", level)
            for model_info in model_infos:
                print(model_info)
