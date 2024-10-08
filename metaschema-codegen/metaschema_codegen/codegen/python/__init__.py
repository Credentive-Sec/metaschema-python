import jinja2
import typing

# Module functions and variables


def _pythonize_name(name: str) -> str:
    """
    Returns the name of the class or variable for a defined assembly, field or flag in a module.
    Makes the name python safe by stripping spaces and converts dashes to underscores.
    This is provided to ensure consistent names when translating from fields to anything else.
    """
    # Some variables have a leading "@" which we don't want
    name = name.removeprefix("@")
    # Strip spaces, convert dashes to underscores
    return f'{name.replace(" ", "").replace("-","_")}'


# Intialize the jinja environment
def _initialize_jinja() -> jinja2.Environment:
    jinja_env = jinja2.Environment(
        loader=jinja2.PackageLoader(package_name="metaschema_codegen.codegen.python")
    )
    return jinja_env


#
# Utility Dataclasses
#


class GlobalReference(typing.NamedTuple):
    """
    A NamedTuple to represent an element exported from a metaschema by being tagged "global". This is used to simplify
    generation of import statements and references in one module to classes defined in another module.

    Elements:
        schema_source (str):  the metaschema defining the global
        module_name (str): the name of the module where this ref will be located
        ref_name (str): the name of the property that will be the "@ref"
        class_name (str): the name of the class that will represent the element referenced
    """

    schema_source: str  # The file where this global is found
    module_name: str  # The python module that will contain this global
    ref_name: str  # How this global will be referenced when it is a property
    class_name: str  # The class name of the element in the module


class ImportItem(typing.NamedTuple):
    module: str
    classes: set[str]


class GeneratedClass(typing.NamedTuple):
    """
    A NamedTuple representing the result of processing a metaschema element

    Elements:
        class_code (str): the code generated by the template for the type of class
        refs (list[str]): the datatypes or external classes actually used by the generated class
    """

    code: str
    refs: list[ImportItem]


class GeneratedConstraint(typing.NamedTuple):
    """
    A Named Tuple representing the result of processing a constraint with a template
    """

    code: str


class Root(typing.NamedTuple):
    """
    A Class to represent a the root of a document that containts a Metaschema compliant structure, used to collect all the metaschema
    assemblies with a 'root-name' attribute. This class is not referenced directly in metascheama, but must exist for a
    root assembly to be JSON serialized by python.
    """

    root_elements: list[str]


class Property:
    def __init__(self, prop_dict: dict[str, str]):
        self.name = _pythonize_name(prop_dict["@name"])
        self.namespace = _pythonize_name(prop_dict["@namespace"])
        self.value = _pythonize_name(prop_dict["@value"])


class CommonTopLevelDefinition:
    """
    A Generator Class to handle Common top-level Instance Data
    """

    def __init__(self, class_dict: dict[str, str | dict[str, str]]):
        # Mandatory values for all instances
        self.common_properties = {}

        keys = class_dict.keys()

        # Name is mandatory so we reference the key directly - it should throw a key error
        # if the key is missing
        self.common_properties["name"] = _pythonize_name(
            typing.cast(str, class_dict["@name"])
        )

        # The following attributes are optional, so we use get which will return None or
        # another default value if we need something else (e.g. empty list)
        if "@deprecated" in keys:
            self.common_properties["deprecated"] = _pythonize_name(
                typing.cast(str, class_dict["@deprecated"])
            )

        if "@scope" in keys:
            self.common_properties["scope"] = _pythonize_name(
                typing.cast(str, class_dict["@scope"])
            )

        if "formal-name" in keys:
            self.common_properties["formal_name"] = _pythonize_name(
                typing.cast(str, class_dict["formal-name"])
            )

        # Don't pythonize description - it's a weird markup field
        self.common_properties["description"] = class_dict.get("description")

        self.common_properties["props"] = [
            Property(prop_dict=typing.cast(dict, prop_dict))
            for prop_dict in class_dict.get("prop", list())
        ]

        self.common_properties["use_name"] = _pythonize_name(
            typing.cast(str, class_dict.get("use-name"))
        )
        self.common_properties["remarks"] = class_dict.get("remarks", dict())

        # Since the "effective name" can either be the "name" or the "use-name"
        # We calculate it here so it can be used elsewhere
        if self.common_properties["use_name"] is not None:
            self.common_properties["effective_name"] = self.common_properties[
                "use_name"
            ]
        else:
            self.common_properties["effective_name"] = self.common_properties["name"]


class CommonInlineDefinition:
    """
    A Generator Class to handle Common inline Instance Data
    """

    def __init__(self, class_dict: dict[str, str | dict[str, str]]):
        self.common_properties = {}

        keys = class_dict.keys()

        # Name is mandatory so we reference the key directly - it should throw a key error
        # if the key is missing
        self.common_properties["name"] = _pythonize_name(
            typing.cast(str, class_dict["@name"])
        )

        # The following attributes are optional, so we use get which will return None or
        # another default value if we need something else (e.g. empty list)
        if "@deprecated" in keys:
            self.common_properties["deprecated"] = _pythonize_name(
                typing.cast(str, class_dict["@deprecated"])
            )

        if "formal-name" in keys:
            self.common_properties["formal_name"] = _pythonize_name(
                typing.cast(str, class_dict["formal-name"])
            )

        # Don't pythonize description - it's a weird markup field
        self.common_properties["description"] = class_dict.get("description")

        self.common_properties["props"] = [
            Property(prop_dict=typing.cast(dict, prop_dict))
            for prop_dict in class_dict.get("prop", list())
        ]

        self.common_properties["use_name"] = _pythonize_name(
            typing.cast(str, class_dict.get("use-name"))
        )
        self.common_properties["remarks"] = class_dict.get("remarks", dict())


class GroupAsParser:
    @staticmethod
    def parse(group_info: dict[str, str]) -> dict[str, str]:
        parsed_dict = {}
        for key, value in group_info.items():
            # Remove leading "@" if it exists
            key = _pythonize_name(key)
            parsed_dict[key] = value

        return parsed_dict
