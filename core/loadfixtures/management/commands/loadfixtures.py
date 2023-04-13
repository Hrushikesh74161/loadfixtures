import re
import os
from collections import defaultdict

from django.core.management import call_command, BaseCommand
from django.db import DEFAULT_DB_ALIAS, models, router
from django.apps import apps
from django.conf import settings


class Command(BaseCommand):
    help = 'Upgrade to loaddata command.'

    def add_arguments(self, parser):
        parser.add_argument(
                '--fixture',
                '-f',
                action="append",
                default=[],
                dest="fixtures",
                help='Fixture labels to load.'
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

    def handle(self, *args, **options):

        self.exclude = set(options["exclude"])
        self.app_labels = set(options["app_labels"])
        self.fixtures = set(options["fixtures"])

        del options["app_labels"]
        del options["fixtures"]

        self.build_graph()

        self.loaddata(*args, **options)

    # topological sorting
    def build_graph(self):
        """
        Builds the relation graph of models.
        """
        # model_label = %(app_name).%(model_name)
        # fixture_info = {
                #     'fixture_label':,
                #     'model_label':,
                #     'model_name':,
                #     'app_name':,
                #     }
        # self.graph = {
            #level : [fixure_info's]
        # }
        self.graph = defaultdict(list)
        # {fixture_label: level}
        lookup_table = dict()
        # [m2m_fixture_info, curr_model_fixture_label, related_model_fixture_label]
        m2m_models = []

        # puts the model in the specific level it belongs to in self.graph
        # and returns its level
        def build(model):
            model_label = model._meta.label_lower
            app_name, model_name = model_label.split('.')
            fixture_label = model_label.replace('.', '_')

            # check if curr model's level is already set
            if fixture_label in lookup_table:
                return lookup_table[fixture_label]
            
            forward_fields = model._meta._forward_fields_map
            # stores models to which current model has either onetoone or manytoone(ForeignKey) relation
            forward_relation_models = set()
            # manytomany relations are set at last

            for field_name,field  in forward_fields.items():
                if isinstance(field, models.ManyToManyField):
                    # default m2m table name created by django
                    default_m2m_model_label = model_label + '_' + field.attname
                    default_m2m_model_name = model_label.split('.')[-1]+"_"+field.attname

                    # if custom m2m model is given, it is mentioned in through attribute of field
                    try:
                        m2m_field = getattr(model, field_name)
                        m2m_model = getattr(m2m_field, 'through')
                        m2m_model_label = m2m_model._meta.label_lower
                        m2m_app_name, m2m_model_name = m2m_model_label.split('.')
                    except AttributeError:
                        m2m_model_label = default_m2m_model_label
                        m2m_model_name = default_m2m_model_name
                        m2m_app_name = app_name

                    m2m_fixture_label = m2m_model_label.replace('.', '_')
                    related_model_fixture_label = field.related_model._meta.label_lower.replace('.', '_')

                    # add m2m tables to self.m2m, at the end we will add these models to graph
                    m2m_fixture_info = {
                            'fixture_label': m2m_fixture_label,
                            'model_label': m2m_model_label,
                            'model_name': m2m_model_name,
                            'app_name': m2m_app_name,
                            }

                    m2m_models.append([m2m_fixture_info, fixture_label, related_model_fixture_label])

                # relations with self are ignored because, django's loaddata command disables constraints
                # while saving a fixture, and later checks the constraints
                elif isinstance(field, (models.ForeignKey, models.OneToOneField)) and field.related_model != model:
                    forward_relation_models.add(field.related_model)

            # if no onetoone or manytoone relations then its level is 0
            level = 0
            if forward_relation_models:
                # builds related models and finds max level of related models
                # and sets current model level to max+1
                level = 1+max(build(related_model) for related_model in forward_relation_models)

            # adding curr models level to lookup table for later usage
            lookup_table[fixture_label] = level

            # insert curr model's fixture info in graph
            fixture_info = {
                    'fixture_label': fixture_label,
                    'model_label': model_label,
                    'model_name': model_name,
                    'app_name': app_name,
                    }
            self.graph[level].append(fixture_info)

            return level

        all_models = apps.get_models()
        for model in all_models:
            build(model)
        
        # populate graph with m2m models
        for m2m in m2m_models:
            level = 1+max(
                lookup_table[m2m[-1]],
                lookup_table[m2m[-2]]
            )
            lookup_table[m2m[0]['fixture_label']] = level
            self.graph[level].append(m2m[0])

    @property
    def levels(self):
        return max(key for key in self.graph)
    
    def loaddata(self, *args, **options):
        for level in range(self.levels+1):
            for fixture_info in self.graph[level]:
                # check if fixture_label's app or model is in exluded
                if fixture_info['model_label'] not in self.exclude and fixture_info['app_name'] not in self.exclude:
                    # if user gave either apps or fixtures explicitly
                    # then only load fixtures of models that are in user given apps and fixtures
                    if self.app_labels or self.fixtures:
                        if fixture_info['app_name'] in self.app_labels or fixture_info['fixture_label'] in self.fixtures:
                            self.load_fixtures(fixture_info, *args, **options)
                    else:
                        self.load_fixtures(fixture_info, *args, **options)

    def load_fixtures(self, fixture_info, *args, **options):
        fixture_files = self.find_fixtures(fixture_info)
        if options['database'] is None:
            options['database'] = self.get_db(fixture_info['model_label'])
        for fixture in fixture_files:
            call_command("loaddata", fixture, **options)

    def find_fixtures(self, fixture_info):
        fixture_files = []
        pattern = r".*\/" + fixture_info['fixture_label'] + r"\..+"
        dirs_to_search = set(settings.FIXTURE_DIRS)
        app_fixtures_folder = self.get_app_path(fixture_info['app_name']) + '/fixtures'
        dirs_to_search.add(app_fixtures_folder)
        for dir in dirs_to_search:
            for root, _, files in os.walk(dir):
                for file in files:
                    match_path = root + '/' + file
                    if re.fullmatch(pattern, match_path):
                        fixture_files.append(match_path)

        return fixture_files

    def get_app_path(self, app):
        app_config = apps.get_app_config(app)
        return app_config.path

    def get_db(self, model):
        if type(model) == str:
            model = apps.get_model(model)
        return router.db_for_write(model)
