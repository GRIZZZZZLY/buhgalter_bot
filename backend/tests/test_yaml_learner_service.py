import textwrap
import pytest
from app.services.yaml_learner_service import YamlLearnerService

SAMPLE_YAML = textwrap.dedent("""\
ru:
  categories:
    - slug: food
      type: expense
      synonyms: [еда, кофе]
    - slug: transport
      type: expense
      synonyms: [такси, метро]
""")


@pytest.fixture
def tmp_yaml(tmp_path):
    p = tmp_path / "categories.yaml"
    p.write_text(SAMPLE_YAML, encoding="utf-8")
    return p


@pytest.fixture
def svc(tmp_yaml):
    return YamlLearnerService(path=tmp_yaml)


def test_add_synonym_success(svc, tmp_yaml):
    result = svc.add_synonym("food", "бургер")
    assert result is True
    content = tmp_yaml.read_text(encoding="utf-8")
    assert "бургер" in content


def test_add_synonym_already_exists(svc, tmp_yaml):
    result = svc.add_synonym("food", "кофе")
    assert result is False
    assert tmp_yaml.read_text(encoding="utf-8").count("кофе") == 1


def test_add_synonym_unknown_slug(svc):
    result = svc.add_synonym("nonexistent", "тест")
    assert result is False


def test_add_category_success(svc, tmp_yaml):
    result = svc.add_category("sport", "expense", ["фитнес", "gym"])
    assert result is True
    content = tmp_yaml.read_text(encoding="utf-8")
    assert "sport" in content
    assert "фитнес" in content


def test_add_category_duplicate_slug(svc):
    result = svc.add_category("food", "expense", ["ещё"])
    assert result is False
