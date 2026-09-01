"""
Regression tests for #1104 and #1105.

#1104: SHACLGenerator used one namespace for two different jobs. `base_uri`
names where the shape resources live, and it was also used to expand every
sh:targetClass and sh:path. With the default `https://semantica.dev/shapes/`
that made shapes target `.../shapes/Person`, while data carries
`.../ns#Person` or the ontology's own class IRI. The shapes matched nothing.
pySHACL then reported conforms=True, because a shape with no focus nodes is
vacuously satisfied, so the mismatch was invisible to the validator the
package ships with.

#1105: a property with no declared domain was attached to every node shape,
which invents a constraint the ontology never stated. With minCount 1 that
makes every instance of every class invalid.

These tests validate real data through pySHACL rather than reading the shapes
text, so a shape that targets nothing cannot pass by being ignored.
"""

import pytest

rdflib = pytest.importorskip("rdflib")
pyshacl = pytest.importorskip("pyshacl")

from rdflib import Graph, RDF, Namespace  # noqa: E402

from semantica.ontology.ontology_generator import SHACLGenerator  # noqa: E402

SH = Namespace("http://www.w3.org/ns/shacl#")
ONTOLOGY_NS = "https://example.org/onto#"
SHAPES_NS = "https://semantica.dev/shapes/"


def _ontology(*, declare_namespace: bool, carry_class_uris: bool):
    """
    Build the same ontology in the shapes the generator can hand over.

    A generated ontology carries class URIs; a hand written one often carries
    only names, and only sometimes declares a namespace. All of them have to
    produce shapes that match the data.
    """
    def class_def(name):
        entry = {"name": name, "label": name}
        if carry_class_uris:
            entry["uri"] = ONTOLOGY_NS + name
        return entry

    def prop_def(name, **extra):
        entry = {"name": name, "type": "datatype", "range": "string", **extra}
        if carry_class_uris:
            entry["uri"] = ONTOLOGY_NS + name
        return entry

    ontology = {
        "classes": [class_def("Person"), class_def("Organization")],
        "properties": [
            prop_def("fullName", domain="Person", required=True),
            # No domain. The ontology never says which class this belongs to.
            prop_def("sourceDocument", required=True),
        ],
    }
    if declare_namespace:
        ontology["namespace"] = {"base_uri": ONTOLOGY_NS}
    return ontology


SHAPES = [
    pytest.param(True, True, id="namespace+uris"),
    pytest.param(True, False, id="namespace-only"),
    pytest.param(False, True, id="uris-only"),
]

# A Person with no fullName. This violates the shape the ontology does state.
VIOLATING_DATA = f"""
@prefix ex: <{ONTOLOGY_NS}> .
ex:alice a ex:Person .
"""

# A Person that satisfies every constraint the ontology actually declares.
CONFORMING_DATA = f"""
@prefix ex: <{ONTOLOGY_NS}> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
ex:bob a ex:Person ;
    ex:fullName "Bob Smith"^^xsd:string .
"""


def _shapes_graph(ontology, **kwargs):
    generator = SHACLGenerator(**kwargs)
    graph = generator.generate(ontology)
    shapes = Graph()
    shapes.parse(data=generator.serialize(graph, "turtle"), format="turtle")
    return shapes


def _validate(data_ttl, shapes_graph):
    data = Graph()
    data.parse(data=data_ttl, format="turtle")
    conforms, _, text = pyshacl.validate(
        data, shacl_graph=shapes_graph, inference="none", advanced=True
    )
    return conforms, text


@pytest.mark.parametrize("declare_namespace,carry_class_uris", SHAPES)
def test_target_class_names_a_class_the_data_can_instantiate(declare_namespace, carry_class_uris):
    shapes = _shapes_graph(_ontology(
        declare_namespace=declare_namespace, carry_class_uris=carry_class_uris
    ))
    targets = {str(o) for o in shapes.objects(None, SH.targetClass)}

    assert targets == {ONTOLOGY_NS + "Person", ONTOLOGY_NS + "Organization"}, targets
    assert not any(t.startswith(SHAPES_NS) for t in targets), (
        f"shapes still target their own shapes namespace: {targets}"
    )


@pytest.mark.parametrize("declare_namespace,carry_class_uris", SHAPES)
def test_property_path_names_a_predicate_the_data_uses(declare_namespace, carry_class_uris):
    shapes = _shapes_graph(_ontology(
        declare_namespace=declare_namespace, carry_class_uris=carry_class_uris
    ))
    paths = {str(o) for o in shapes.objects(None, SH.path)}

    assert paths, "no sh:path emitted at all"
    for path in paths:
        assert path.startswith(ONTOLOGY_NS), path


@pytest.mark.parametrize("declare_namespace,carry_class_uris", SHAPES)
def test_a_real_violation_is_actually_reported(declare_namespace, carry_class_uris):
    """The killer case. Shapes that match nothing make pySHACL return conforms=True."""
    shapes = _shapes_graph(_ontology(
        declare_namespace=declare_namespace, carry_class_uris=carry_class_uris
    ))
    conforms, text = _validate(VIOLATING_DATA, shapes)

    assert not conforms, (
        "a Person with no fullName was reported as conforming, which means the "
        f"shapes matched no focus nodes:\n{text}"
    )
    assert "fullName" in text


@pytest.mark.parametrize("declare_namespace,carry_class_uris", SHAPES)
def test_conforming_data_still_conforms(declare_namespace, carry_class_uris):
    shapes = _shapes_graph(_ontology(
        declare_namespace=declare_namespace, carry_class_uris=carry_class_uris
    ))
    conforms, text = _validate(CONFORMING_DATA, shapes)
    assert conforms, text


def test_default_target_namespace_is_the_vocabulary_not_the_shapes_namespace():
    """With nothing declared anywhere, targets must not land in the shapes namespace."""
    ontology = {
        "classes": [{"name": "Person", "label": "Person"}],
        "properties": [{"name": "fullName", "type": "datatype", "range": "string",
                        "domain": "Person", "required": True}],
    }
    shapes = _shapes_graph(ontology)
    targets = {str(o) for o in shapes.objects(None, SH.targetClass)}

    assert targets, "no sh:targetClass emitted at all"
    for target in targets:
        assert not target.startswith(SHAPES_NS), target


def test_shape_resources_are_distinct_from_the_classes_they_target():
    shapes = _shapes_graph(_ontology(declare_namespace=True, carry_class_uris=True))
    node_shapes = {str(s) for s in shapes.subjects(RDF.type, SH.NodeShape)}
    targets = {str(o) for o in shapes.objects(None, SH.targetClass)}

    assert node_shapes, "no node shapes emitted"
    assert node_shapes.isdisjoint(targets), (
        f"a shape and the class it targets are the same resource: {node_shapes & targets}"
    )


# ── #1105 ────────────────────────────────────────────────────────────────────

def test_domainless_property_is_not_asserted_on_every_class():
    """minCount 1 on a domain-less property invalidates every instance of every class."""
    generator = SHACLGenerator()
    graph = generator.generate(_ontology(declare_namespace=True, carry_class_uris=True))

    carriers = [
        shape.target_class
        for shape in graph.node_shapes
        for prop in shape.property_shapes
        if prop.path.endswith("sourceDocument")
    ]
    assert carriers == [], f"a property with no declared domain was attached to {carriers}"


def test_domainless_property_does_not_invalidate_conforming_data():
    shapes = _shapes_graph(_ontology(declare_namespace=True, carry_class_uris=True))
    conforms, text = _validate(CONFORMING_DATA, shapes)

    assert conforms, f"invented a constraint the ontology never declared:\n{text}"
    assert "sourceDocument" not in text


def test_domainless_attachment_is_available_as_an_explicit_opt_in():
    """The old behaviour stays reachable for anyone who relied on it."""
    generator = SHACLGenerator(attach_domainless_properties=True)
    graph = generator.generate(_ontology(declare_namespace=True, carry_class_uris=True))

    carriers = {
        shape.target_class
        for shape in graph.node_shapes
        for prop in shape.property_shapes
        if prop.path.endswith("sourceDocument")
    }
    assert len(carriers) == len(graph.node_shapes)


# ── Review findings on the first revision of this fix ────────────────────────

@pytest.mark.parametrize("fmt,parse_as", [
    ("turtle", "turtle"), ("n-triples", "nt"), ("json-ld", "json-ld"),
])
def test_every_format_targets_the_ontology_namespace(fmt, parse_as):
    """
    The first revision fixed Turtle alone. JSON-LD and N-Triples went on
    pasting names onto the shapes namespace, so two of the three formats still
    produced shapes that matched nothing.
    """
    generator = SHACLGenerator()
    graph = generator.generate(_ontology(declare_namespace=False, carry_class_uris=True))

    shapes = Graph()
    shapes.parse(data=generator.serialize(graph, fmt), format=parse_as)
    targets = {str(o) for o in shapes.objects(None, SH.targetClass)}

    assert targets == {ONTOLOGY_NS + "Person", ONTOLOGY_NS + "Organization"}, targets
    assert not any(t.startswith(SHAPES_NS) for t in targets), targets


@pytest.mark.parametrize("fmt,parse_as", [
    ("turtle", "turtle"), ("n-triples", "nt"), ("json-ld", "json-ld"),
])
def test_every_format_reports_a_real_violation(fmt, parse_as):
    generator = SHACLGenerator()
    graph = generator.generate(_ontology(declare_namespace=False, carry_class_uris=True))

    shapes = Graph()
    shapes.parse(data=generator.serialize(graph, fmt), format=parse_as)
    conforms, text = _validate(VIOLATING_DATA, shapes)

    assert not conforms, f"{fmt} shapes matched no focus nodes:\n{text}"


def test_a_property_sharing_a_class_name_keeps_its_own_iri():
    """One name-keyed map gave the property the class's IRI, so sh:path validated
    the wrong predicate."""
    ontology = {
        "classes": [{"name": "Account", "uri": ONTOLOGY_NS + "Account"}],
        "properties": [
            {
                "name": "Account",
                "uri": ONTOLOGY_NS + "accountNumber",
                "type": "datatype",
                "range": "string",
                "domain": "Account",
                "required": True,
            }
        ],
    }
    shapes = _shapes_graph(ontology)

    paths = {str(o) for o in shapes.objects(None, SH.path)}
    targets = {str(o) for o in shapes.objects(None, SH.targetClass)}

    assert paths == {ONTOLOGY_NS + "accountNumber"}, paths
    assert targets == {ONTOLOGY_NS + "Account"}, targets


def test_sh_class_resolves_to_the_class_namespace():
    ontology = {
        "classes": [
            {"name": "Person", "uri": ONTOLOGY_NS + "Person"},
            {"name": "Organization", "uri": ONTOLOGY_NS + "Organization"},
        ],
        "properties": [
            {
                "name": "worksAt",
                "uri": ONTOLOGY_NS + "worksAt",
                "type": "object",
                "range": "Organization",
                "domain": "Person",
            }
        ],
    }
    shapes = _shapes_graph(ontology)
    classes = {str(o) for o in shapes.objects(None, SH["class"])}

    assert classes == {ONTOLOGY_NS + "Organization"}, classes


def test_the_engine_forwards_the_new_options():
    """to_shacl passed them through generate(**options), which never reads them."""
    from semantica.ontology.engine import OntologyEngine

    ontology = _ontology(declare_namespace=False, carry_class_uris=False)

    turtle = OntologyEngine().to_shacl(ontology, target_namespace="https://forwarded.example/ns#")
    shapes = Graph()
    shapes.parse(data=turtle, format="turtle")
    targets = {str(o) for o in shapes.objects(None, SH.targetClass)}
    assert all(t.startswith("https://forwarded.example/ns#") for t in targets), targets

    attached = OntologyEngine().to_shacl(ontology, attach_domainless_properties=True)
    assert "sourceDocument" in attached

    default = OntologyEngine().to_shacl(ontology)
    assert "sourceDocument" not in default


def test_the_opt_in_warns_rather_than_whispering(caplog):
    import logging

    with caplog.at_level(logging.WARNING):
        SHACLGenerator(attach_domainless_properties=True).generate(
            _ontology(declare_namespace=True, carry_class_uris=True)
        )

    messages = " ".join(record.getMessage() for record in caplog.records)
    assert "sourceDocument" in messages
