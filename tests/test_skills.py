from commands import CommandContext, command_specs, handle_command, parse_command
from skills import clear_skills, discover_skills, get_skill, list_skills, load_skills_from_dir
from skills_bundled import register_bundled_skills


class DummyEngine:
    def set_messages(self, messages):
        self.messages = messages


def setup_function() -> None:
    clear_skills()


def teardown_function() -> None:
    clear_skills()


def test_register_bundled_skills() -> None:
    register_bundled_skills()

    assert sorted(skill.name for skill in list_skills()) == ["commit", "review", "simplify", "test"]
    assert "Code Review" in get_skill("review").get_prompt("")
    assert "Additional Focus" in get_skill("review").get_prompt("security")


def test_parse_command_supports_skill_like_commands() -> None:
    assert parse_command("/review security") == ("review", "security")


def test_skill_command_returns_pending_query(tmp_path) -> None:
    register_bundled_skills()
    ctx = CommandContext(
        engine=DummyEngine(),  # type: ignore[arg-type]
        session_store=None,  # type: ignore[arg-type]
        session_dir=str(tmp_path),
        cwd=str(tmp_path),
        model="mock-sonnet",
    )

    result = handle_command("review", "security", ctx)

    assert result.pending_query is not None
    assert "Code Review" in result.pending_query
    assert "security" in result.pending_query


def test_skills_command_lists_available_skills(capsys, tmp_path) -> None:
    register_bundled_skills()
    ctx = CommandContext(
        engine=DummyEngine(),  # type: ignore[arg-type]
        session_store=None,  # type: ignore[arg-type]
        session_dir=str(tmp_path),
        cwd=str(tmp_path),
        model="mock-sonnet",
    )

    handle_command("skills", "", ctx)

    output = capsys.readouterr().out
    assert "/review" in output
    assert "bundled" in output


def test_command_specs_include_registered_skills() -> None:
    register_bundled_skills()

    specs = [name for name, _description in command_specs()]

    assert any(name.startswith("review") for name in specs)
    assert any(name.startswith("commit") for name in specs)


def test_load_project_skill_from_directory(tmp_path) -> None:
    skill_dir = tmp_path / "skills" / "audit"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "name: audit\n"
        "description: Audit changed files\n"
        "arguments: focus\n"
        "---\n"
        "Audit this area: $ARGUMENTS",
        encoding="utf-8",
    )

    loaded = load_skills_from_dir(tmp_path / "skills")

    assert [skill.name for skill in loaded] == ["audit"]
    assert get_skill("audit").get_prompt("auth") == "Audit this area: auth"


def test_discover_project_skills(tmp_path) -> None:
    skill_dir = tmp_path / ".fireseed" / "skills" / "check"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("Check project details", encoding="utf-8")

    loaded = discover_skills(str(tmp_path))

    assert [skill.name for skill in loaded] == ["check"]
