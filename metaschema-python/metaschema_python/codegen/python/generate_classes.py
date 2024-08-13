from __future__ import annotations
import urllib.parse

import jinja2
from importlib import resources
from typing import NamedTuple, cast
from pathlib import Path

import datetime
import urllib

from . import pkg_resources

from .. import CodeGenException

from ...core.schemaparse import (
    MetaSchemaSet,
    Metaschema,
    DataType,
    SimpleRestrictionDatatype,
    ComplexDataType,
)


# Module functions and variables


def _pythonize_name(name: str) -> str:
    """
    Returns the name of the class or variable for a defined assembly, field or flag in a module.
    Makes the name python safe by stripping spaces and converts dashes to underscores.
    This is provided to ensure consistent names when translating from fields to anything else.
    """
    # Strip spaces, convert dashes to underscores
    return f'{name.replace(" ", "").replace("-","_")}'


# Intialize the jinja environment
jinja_env = jinja2.Environment(
    loader=jinja2.PackageLoader(package_name="metaschema_python.codegen.python")
)


# Utility Classes


class GlobalReference(NamedTuple):
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


class GeneratedClass(NamedTuple):
    """
    A NamedTuple representing the result of processing a metaschema element

    Elements:
        class_code (str): the code generated by the template for the type of class
        refs (list[str]): the datatypes or external classes actually used by the generated class
    """

    code: str
    refs: list[str]


class GeneratedConstraint(NamedTuple):
    """
    A Named Tuple representing the result of processing a constraint with a template
    """

    code: str


class Root(NamedTuple):
    """
    A Class to represent a the root of a document that containts a Metaschema compliant structure, used to collect all the metaschema
    assemblies with a 'root-name' attribute. This class is not referenced directly in metascheama, but must exist for a
    root assembly to be JSON serialized by python.
    """

    root_elements: list[str]


class ImportItem(NamedTuple):
    module: str
    classes: list[str]


# Classes to parse the metaschemaset


class PackageGenerator:
    """
    This class is initialized with a MetaSchemaSet and generates a package with Python source
    code for each of the metaschemas.
    """

    def __init__(
        self,
        parsed_metaschemas: MetaSchemaSet,
        destination_directory: Path,
        package_name: str,
        ignore_existing_files: bool = False,
    ) -> None:
        """
            This class is initialized with a MetaSchemaSet and generates a package with Python source
        code for each of the metaschemas.

            Args:
                parsed_metaschemas (MetaSchemaSet): The metaschemas parsed by the schemaparse module
                destination_directory (Path): The directory to write the generated code to
                package_name (str): the name of the package containing the modules
                ignore_existing_files (bool, optional): Whether to ignore existing directories and files. If true, will overwrite. If false will throw an exception. Defaults to False.
        """
        # initialize the package
        self.metaschema_set = parsed_metaschemas
        self.destination = destination_directory
        self.package_name = package_name
        self.module_generators: list[ModuleGenerator | DatatypeModuleGenerator] = []

        # generate code for all of the core datatypes
        self.generate_datatype_module()

        # collect all the elements of each metaschema which might be used across modules
        # and put them into a dictionary that can be passed to the module/class generators
        self.gather_references()

        # generate modules for all of the schemas parsed.
        # self.generate_schema_modules()

        # write the generated code to files in a directory.
        self.write_package(ignore_existing_files=ignore_existing_files)

    def gather_references(self):
        """
        This function parses all of the metaschema global elements that each metaschema exports for reference in
        other schemas through "import". For each global element it creates a GlobalRef object with attributes
        that can be used to generate import statements in the python modules we generate. It also creates
        GlobalRef objects for datatypes since those are used by all modules.
        """
        self.global_refs: list[GlobalReference] = []
        for metaschema in self.metaschema_set.metaschemas:
            schema_source = str(metaschema.file)
            module_name = _pythonize_name(metaschema.short_name)
            for global_reference_key in metaschema.globals.keys():
                self.global_refs.append(
                    GlobalReference(
                        schema_source=schema_source,
                        module_name=module_name,
                        ref_name=_pythonize_name(global_reference_key),
                        class_name=_pythonize_name(
                            metaschema.globals[global_reference_key]
                        ),
                    )
                )

        # add references for metaschema datatypes, they look a little strange because
        # they're in the metaschema xsd, not a specific metaschema
        for datatype in self.metaschema_set.datatypes:
            if datatype.ref_name is not None:
                self.global_refs.append(
                    GlobalReference(
                        schema_source="datatype",
                        module_name="datatypes",
                        ref_name=_pythonize_name(datatype.ref_name),
                        class_name=_pythonize_name(datatype.name),
                    )
                )

    def generate_datatype_module(self):
        self.module_generators.append(
            DatatypeModuleGenerator(datatypes=self.metaschema_set.datatypes)
        )

    def generate_schema_modules(self):
        for metaschema in self.metaschema_set.metaschemas:
            self.module_generators.append(
                ModuleGenerator(
                    metaschema=metaschema,
                    global_refs=self.global_refs,
                )
            )

    # TODO: create a directory corresponding the the metaschema namespace (top level assembly "root-name") (makes a python package)
    def write_package(self, ignore_existing_files: bool) -> None:
        """
        Writes all the files in the package to files at a location provided.

        Note that we assume that thePath exists and represents an empty directory that can be written to.
        The caller is responsible for verifying that this is correct before giving us the path.
        We will raise Exceptions if anything doesn't work.
        """

        # check the destination directory.
        try:
            self._check_directory(self.destination, ignore_existing_files)
        except CodeGenException as e:
            raise CodeGenException(f"Error when checking destination directory: {e}")

        # create the directory Path by appending the provided base path and the provided package name
        package_path = Path(self.destination, self.package_name)

        package_path.mkdir(exist_ok=ignore_existing_files)

        pkg_init = resources.files(pkg_resources).joinpath("pkg.__init__.py")
        with resources.as_file(pkg_init) as init_file:
            package_path.joinpath("__init__.py").write_text(init_file.read_text())

        pkg_base_classes = resources.files(pkg_resources).joinpath(
            "pkg.base_classes.py"
        )
        with resources.as_file(pkg_base_classes) as base_classes_file:
            package_path.joinpath("base_classes.py").write_text(
                base_classes_file.read_text()
            )

        for module_generator in self.module_generators:
            module_file = package_path.joinpath(
                Path(f"{module_generator.module_name}.py")
            )
            module_file.write_text(module_generator.generated_module)

    def _check_directory(
        self, path_to_check: Path, ignore_existing_files: bool
    ) -> None:
        """
        Checks to make sure that a Path exists and represents and empty directory.
        Raises an exeption if this not true

        Args:
            path_to_check (Path): the Path to check.
        """
        if not path_to_check.exists():
            raise CodeGenException(f"{str(path_to_check)} does not exist.")

        if not path_to_check.is_dir():
            raise CodeGenException(
                f"{str(path_to_check)} exists but is not a directory."
            )

        if ignore_existing_files is False and len(list(path_to_check.iterdir())) > 0:
            raise CodeGenException(f"{str(path_to_check)} exists but is not empty.")


class ModuleGenerator:
    """
    A class to generate a python source code file (module) from a parsed metaschema. It will contain a class for
    every instance in the metaschema.
    It converts a data object representing a generic metaschema to a python oriented dictionary to pass to a template.
    """

    def __init__(
        self, metaschema: Metaschema, global_refs: list[GlobalReference]
    ) -> None:
        self.metaschema = metaschema
        self.version = cast(str, metaschema.schema_dict["schema-version"])
        self.module_name = _pythonize_name(
            cast(str, metaschema.schema_dict["short-name"])
        )
        self.module_imports = []
        self.generated_classes: list[GeneratedClass] = []

        #
        # The first pass is to generate the list of elements imported by or defined in the metaschema so that we can
        # identify the appropriate class for a "@ref"
        #

        # get a list of elements from imports that could be referenced with a "@ref" in this module
        # The form will be {@ref: module.Class}
        module_refs: dict[str, str] = {}

        # Add the refs to datatypes
        module_refs.update(
            {
                global_ref.ref_name: f"{global_ref.module_name}.{global_ref.class_name}"
                for global_ref in global_refs
                if global_ref.schema_source == "datatype"
            }
        )

        # get the list of imported schemas and add all the relevant global refs
        imported_schemas = [
            _import["@href"]
            for _import in self.metaschema.schema_dict.get("import", [])
        ]

        for schema in imported_schemas:
            module_refs.update(
                {
                    global_ref.ref_name: f"{global_ref.module_name}.{global_ref.class_name}"
                    for global_ref in global_refs
                    if global_ref.schema_source == schema
                }
            )

        # record all of the top-level assemblies, flags and fields in this metaschema to include as local refs
        # Note that a locally defined instance's @ref will overwrite an import @ref, which I think is the correct behavior

        for assembly in self.metaschema.schema_dict.get("define-assembly", []):
            module_refs[f'{_pythonize_name(assembly["@name"])}'] = (
                f'{_pythonize_name(assembly["formal-name"])}'
            )

        for field in self.metaschema.schema_dict.get("define-field", []):
            module_refs[f'{_pythonize_name(field["@name"])}'] = (
                f'{_pythonize_name(field["formal-name"])}'
            )

        for flag in self.metaschema.schema_dict.get("define-flag", []):
            module_refs[f'{_pythonize_name(flag["@name"])}'] = (
                f'{_pythonize_name(flag["formal-name"])}'
            )

        #
        # Second Pass: With our ref dictionary in place, we perform a deeper pars to actually generate the classes.
        #

        for flag in self.metaschema.schema_dict.get("define-flag", []):
            self.generated_classes.append(
                FlagClassGenerator(class_dict=flag, refs=module_refs).generated_class
            )

        for field in self.metaschema.schema_dict.get("define-field", []):
            self.generated_classes.append(
                FieldClassGenerator(class_dict=field, refs=module_refs).generated_class
            )

        # With the classes generated, we create a Set to contain import strings for the imports that are actually used by
        # the classes in the module, it's a set since we only need to import once.

        imports = set()

        for generated_class in self.generated_classes:
            imports.update(generated_class.refs)

        # Finally, we are ready to generate the module source
        template_context = {}
        template_context["imports"] = imports
        template_context["classes"] = [
            generated_class.code for generated_class in self.generated_classes
        ]

        template = jinja_env.get_template("module.py.jinja2")

        self.generated_module = template.render(template_context)


class FlagClassGenerator:
    """
    A class to generate a flag object from parsed metaschema flag data
    """

    def __init__(self, class_dict: dict, refs: dict[str, str]) -> None:
        # Parse flag data, and produce a GeneratedClass object

        # look up the datatype class in the class_dict
        datatype = class_dict["@as-type"]
        datatype_class = refs[datatype]

        # Identify the class representing the datatype
        template_context = {}
        template_context["flag_name"] = _pythonize_name(class_dict["@name"])
        template_context["class_name"] = _pythonize_name(class_dict["formal-name"])
        template_context["datatype"] = datatype_class
        template_context["description"] = class_dict.get("description", None)

        # Build constraints
        constraint_classes = ConstraintGenerator(
            constraint_dict=class_dict.get("constraint", {})
        ).constraint_classes
        template_context["constraints"] = constraint_classes

        template = jinja_env.get_template("class_flag.py.jinja2")

        class_code = template.render(template_context)

        self.generated_class = GeneratedClass(
            code=class_code,
            refs=[datatype_class],
        )


class FieldClassGenerator:
    """
    A class to generate a field object from parsed metaschema flag data
    """

    def __init__(self, class_dict: dict, refs: dict[str, str]) -> None:
        data_type = class_dict["@as-type"]
        datatype_ref = refs[data_type]

        template_context = {}
        template_context["field_name"] = class_dict["@name"]
        template_context["data_type"] = data_type
        template_context["class_name"] = class_dict["formal-name"]
        template_context["description"] = class_dict.get("description")
        props = []
        for prop in class_dict.get("prop", []):
            props.append(
                {
                    "name": prop["@name"],
                    "value": prop["@value"],
                    "namespace": prop.get(
                        "@namespace", "http://csrc.nist.gov/ns/oscal/metaschema/1.0"
                    ),
                }
            )
        template_context["properties"] = props

        inline_flags = []
        if "define-flag" in class_dict.keys():
            for flag in class_dict["define-flag"]:
                inline_flags.append(
                    FlagClassGenerator(class_dict=flag, refs=refs).generated_class
                )

        template_context["inline-flags"] = inline_flags

        template = jinja_env.get_template("class_field.py.jinja2")
        self.generated_class = GeneratedClass(
            code=template.render(template_context),
            refs=[datatype_ref],
        )


class ConstraintGenerator:
    """
    A class to convert a constraint into a format that can be fed to a code generation template.
    """

    def __init__(self, constraint_dict: dict[str, dict]):
        """
        __init__ Recursively parses a constraint and produces a template context.

        Args:
            constraint_dict (dict): "constraint" dictionary parsed from a metaschema element.
        """
        # TODO: This is extremely primitive! We will do better when we have a more defined
        # approach for constraints
        self.constraint_classes = []

        for type, properties in constraint_dict.items():
            template_context = {}
            template_context["type"] = _pythonize_name(type)
            template_context["name"] = properties[0].get("@name")
            template_context["target"] = properties[0].get("@target", ".")
            template_context["level"] = properties[0].get("@level", "ERROR")
            self.constraint_classes.append(
                self._generate(template_context=template_context)
            )

    def _generate(self, template_context: dict) -> str:
        template = jinja_env.get_template("constraints.py.jinja2")
        constraint_class = template.render(template_context)
        return constraint_class


class DatatypeModuleGenerator:
    """
    A class to generate the datatypes module, including all of the datatypes classes related to the models
    """

    def __init__(self, datatypes: list[DataType]) -> None:
        generatedclasses: list[str] = []
        # Generate the simple type classes

        # Map XML datatypes to python built-in types
        # This ignores any restrictions, e.g a positiveInteger is an int
        TYPE_MAP = {
            "anyURI": urllib.parse.ParseResult,
            "base64Binary": str,
            "boolean": bool,
            "date": datetime.date,
            "dateTime": datetime.datetime,
            "decimal": float,
            "duration": datetime.timedelta,
            "integer": int,
            "nonNegativeInteger": int,
            "positiveInteger": int,
            "string": str,
            "token": str,
        }

        # Metaschema datatypes can inherit from each other, or from an xml datatype.
        # We only count the "parent" datatype for purposes of inheritance if a datatype inherits from a
        # metaschema datatype.
        metaschema_parents = [datatype.name for datatype in datatypes]

        for datatype in datatypes:
            if isinstance(datatype, SimpleRestrictionDatatype):
                datatype_dict = {}
                if datatype.base_type in metaschema_parents:
                    datatype_dict["parent"] = datatype.base_type

                datatype_dict["documentation"] = datatype.documentation

                datatype_dict["name"] = datatype.name

                datatype_dict["pattern"] = datatype.patterns["pcre"]

                generatedclasses.extend(
                    SimpleDatatypeClassGenerator(
                        datatype_dict=datatype_dict
                    ).generated_class
                )
            elif isinstance(datatype, ComplexDataType):
                datatype_dict = {}

                datatype_dict["documentation"] = datatype.documentation

                datatype_dict["name"] = datatype.name

                datatype_dict["elements"] = datatype.elements

                generatedclasses.extend(
                    ComplexDatatypesGenerator(
                        datatype_dict=datatype_dict
                    ).generated_class
                )

            else:
                raise CodeGenException(
                    "Unidentified dataclass type" + datatype.__class__.__name__
                )

        # Finally, we are ready to generate the module source
        template_context = {}
        template_context["imports"] = [
            ImportItem(
                module=".base_classes", classes=["SimpleDatatype", "ComplexDataType"]
            ),
            ImportItem(module="re", classes=["Pattern", "compile"]),
        ]

        template_context["classes"] = generatedclasses

        template = jinja_env.get_template("module.py.jinja2")

        self.module_name = "datatypes"
        self.generated_module = template.render(template_context)


class SimpleDatatypeClassGenerator:
    """
    A class to convert the Metaschema Datatypes into classes
    """

    def __init__(self, datatype_dict: dict[str, str]):
        # process the datatypes to make the template context to pass to the template
        template = jinja_env.get_template("class_datatype_simple.py.jinja2")

        self.generated_class = template.render(datatype=datatype_dict)


class ComplexDatatypesGenerator:
    """
    A class to convert the Metaschema Datatypes into classes
    """

    # class ComplexDataType:
    # ref_name: str
    # class_name: str
    # elements: list[SimpleDataType | ComplexDataType]
    # description: str | None = None

    def __init__(self, datatype_dict: dict[str, str | list[str]]):
        # process the datatypes to make the template context to pass to the template
        template_context = {}

        template = jinja_env.get_template("class_datatype_complex.py.jinja2")

        self.generated_class = template.render(datatype=datatype_dict)