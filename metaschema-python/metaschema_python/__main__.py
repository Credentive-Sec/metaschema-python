import argparse
import sys

from .core.metaschema_parser import MetaschemaParser


# Parse the command arguments
parser = argparse.ArgumentParser(
    prog="metaschema_parser",
    description="Parse an XML based metaschema and generate Python objects.",
)
parser.add_argument(
    "location",
    type=str,
    help="A filename or url for the base metaschema file.",
)
parser.add_argument(
    "-B",
    "--base",
    dest="base",
    help="[optional] A base URL or directory for obtaining other child schemas. If this is not provided, it will be inferred from the filename.",
)
parser.add_argument(
    "-S",
    "--schema",
    dest="schema",
    help="[optional] The location of the metaschema xsd file.",
)

args = parser.parse_args()


# Parse all of the metaschema definitions into trees.
try:
    metaschema_parser = MetaschemaParser(
        location=args.location,
        schema_file="/home/vscode/metaschema-python/metaschema/schema/xml/metaschema.xsd",
    )
    metaschema_contents = metaschema_parser.parse()


except Exception as e:
    print("Error parsing metaschema:", e)
    sys.exit(1)
