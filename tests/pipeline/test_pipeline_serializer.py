import json

import pytest

from semantica.pipeline.pipeline_builder import PipelineBuilder, PipelineSerializer


@pytest.mark.parametrize("serialization_format", ["dict", "json"])
def test_roundtrip_preserves_step_dependencies(serialization_format):
    builder = PipelineBuilder()
    builder.add_step("extract", "source")
    builder.add_step("index", "sink")
    builder.connect_steps("extract", "index")
    pipeline = builder.build("indexing")

    serializer = PipelineSerializer()
    serialized = serializer.serialize_pipeline(pipeline, format=serialization_format)
    restored = serializer.deserialize_pipeline(serialized)

    index_step = next(step for step in restored.steps if step.name == "index")
    assert index_step.dependencies == ["extract"]


@pytest.mark.parametrize("serialization_format", ["dict", "json"])
def test_deserialization_accepts_dependencies_in_legacy_config(serialization_format):
    serialized = {
        "name": "legacy-indexing",
        "steps": [
            {"name": "extract", "type": "source", "config": {}},
            {
                "name": "index",
                "type": "sink",
                "config": {"dependencies": ["extract"]},
            },
        ],
    }
    if serialization_format == "json":
        serialized = json.dumps(serialized)

    restored = PipelineSerializer().deserialize_pipeline(serialized)

    index_step = next(step for step in restored.steps if step.name == "index")
    assert index_step.dependencies == ["extract"]
    assert index_step.config == {}
