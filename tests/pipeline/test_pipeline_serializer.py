import copy
import json

import pytest

from semantica.pipeline.pipeline_builder import PipelineBuilder, PipelineSerializer


@pytest.mark.parametrize("serialization_format", ["dict", "json"])
def test_roundtrip_preserves_dependencies_and_delta_metadata(serialization_format):
    builder = PipelineBuilder()
    builder.add_step("extract", "source")
    builder.add_step(
        "index",
        "sink",
        delta_mode=True,
        base_version_id="v1",
        target_version_id="v2",
    )
    builder.connect_steps("extract", "index")
    pipeline = builder.build("incremental-index")

    serializer = PipelineSerializer()
    serialized = serializer.serialize_pipeline(pipeline, format=serialization_format)
    restored = serializer.deserialize_pipeline(serialized)

    index_step = next(step for step in restored.steps if step.name == "index")
    assert index_step.dependencies == ["extract"]
    assert index_step.delta_mode is True
    assert index_step.base_version_id == "v1"
    assert index_step.target_version_id == "v2"


@pytest.mark.parametrize("serialization_format", ["dict", "json"])
def test_serialization_omits_runtime_handlers(serialization_format):
    def handler(data, **config):
        return data

    builder = PipelineBuilder()
    builder.add_step("extract", "source", handler=handler, batch_size=10)
    pipeline = builder.build("handler-pipeline")

    serializer = PipelineSerializer()
    serialized = serializer.serialize_pipeline(pipeline, format=serialization_format)
    serialized_data = (
        json.loads(serialized) if isinstance(serialized, str) else serialized
    )

    assert serialized_data["steps"][0]["config"] == {"batch_size": 10}

    restored = serializer.deserialize_pipeline(serialized)
    assert restored.steps[0].handler is None
    assert restored.steps[0].config == {"batch_size": 10}


def test_deserialization_ignores_legacy_stringified_handler():
    serialized = json.dumps(
        {
            "name": "legacy-handler-pipeline",
            "steps": [
                {
                    "name": "extract",
                    "type": "source",
                    "config": {
                        "handler": "<function extract at 0x1234>",
                        "batch_size": 10,
                    },
                    "dependencies": [],
                }
            ],
        }
    )

    restored = PipelineSerializer().deserialize_pipeline(serialized)

    assert restored.steps[0].handler is None
    assert restored.steps[0].config == {"batch_size": 10}


def test_deserialization_does_not_mutate_caller_owned_dict():
    payload = {
        "name": "legacy-handler-pipeline",
        "steps": [
            {
                "name": "extract",
                "type": "source",
                "config": {
                    "handler": "<function extract at 0x1234>",
                    "batch_size": 10,
                },
                "dependencies": [],
            }
        ],
    }
    snapshot = copy.deepcopy(payload)

    restored = PipelineSerializer().deserialize_pipeline(payload)

    assert payload == snapshot
    assert "handler" in payload["steps"][0]["config"]
    assert payload is not snapshot
    assert restored.steps[0].handler is None
    assert restored.steps[0].config == {"batch_size": 10}
