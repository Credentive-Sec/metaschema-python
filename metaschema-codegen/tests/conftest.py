import pytest

from metaschema_codegen.core.schemaparse import MetaschemaSetParser
from metaschema_codegen.codegen.python.codegen import PackageGenerator
from pathlib import Path


@pytest.fixture(scope="module")
def parsed_metaschema():
    ms = MetaschemaSetParser(
        metaschema_location="OSCAL/src/metaschema/oscal_complete_metaschema.xml"
    ).metaschema_set
    return ms

@pytest.fixture(scope="module")
def generated_package(parsed_metaschema):
    output_path = Path("test-output")
    if not output_path.exists():
        output_path.mkdir()
    pg = PackageGenerator(
        parsed_metaschema,
        output_path,
        package_name="oscal",
        ignore_existing_files=True,
    )
    return pg
