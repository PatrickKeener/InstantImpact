from instantimpact_common.safety import validate_for_enqueue
from instantimpact_common.toolkit import find_trained_weights, render_flux_lora_yaml


def test_yaml_includes_trigger_and_paths():
    y = render_flux_lora_yaml(
        name="ii_aria_v1",
        trigger_word="sks_aria_v1",
        dataset_dir="/data/characters/x/versions/v001/dataset",
        training_folder="/data/characters/x/versions/v001/lora/toolkit_run",
        steps=1500,
    )
    assert "sks_aria_v1" in y
    assert "ii_aria_v1" in y
    assert "sd_trainer" in y
    assert "is_flux: true" in y
    assert "/data/characters/x/versions/v001/dataset" in y
    assert "steps: 1500" in y


def test_lora_train_allowed_while_training_status():
    r = validate_for_enqueue(
        job_type="lora_train",
        character_status="training",
        synthetic_confirmed=True,
        age_appearance_min=21,
        not_real_person_attested=True,
    )
    assert r.ok


def test_find_weights_picks_named_file(tmp_path):
    run = tmp_path / "run" / "ii_x"
    run.mkdir(parents=True)
    (run / "ii_x.safetensors").write_bytes(b"a" * 100)
    (run / "ii_x_000000250.safetensors").write_bytes(b"b" * 50)
    found = find_trained_weights(tmp_path / "run", "ii_x")
    assert found is not None
    assert found.name == "ii_x.safetensors"
