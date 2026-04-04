from godot_agent.llm.client import Message, ToolCall
from godot_agent.runtime.session import list_sessions, load_latest_session, load_session, save_session


class TestSessions:
    def test_save_and_load_roundtrip(self, tmp_path):
        messages = [
            Message.system("system"),
            Message.user("Explain the HUD"),
            Message.assistant(
                content="Let me inspect that.",
                tool_calls=[ToolCall(id="c1", name="read_file", arguments='{"path": "/tmp/hud.gd"}')],
            ),
            Message.tool_result("c1", '{"content": "ok"}'),
            Message.assistant(content="HUD summary"),
        ]

        save_session(
            str(tmp_path),
            "abc123",
            messages,
            project_path="/tmp/project",
            project_name="Demo",
            model="gpt-5.4",
            mode="review",
            skill_mode="hybrid",
            enabled_skills=["collision"],
            disabled_skills=["physics"],
            active_skills=["collision"],
            gameplay_intent={"genre": "bullet_hell", "enemy_model": "scripted_patterns", "confirmed": True},
        )

        record = load_session(str(tmp_path), "abc123")
        assert record is not None
        assert record.project_name == "Demo"
        assert record.mode == "review"
        assert record.skill_mode == "hybrid"
        assert record.enabled_skills == ["collision"]
        assert record.disabled_skills == ["physics"]
        assert record.active_skills == ["collision"]
        assert record.gameplay_intent["genre"] == "bullet_hell"
        assert record.message_count == len(messages)
        assert record.messages[2].tool_calls is not None
        assert record.messages[2].tool_calls[0].name == "read_file"

    def test_list_and_filter_sessions(self, tmp_path):
        save_session(
            str(tmp_path),
            "one",
            [Message.system("system"), Message.user("First task")],
            project_path="/tmp/one",
            project_name="One",
            model="gpt-5.4",
            mode="apply",
        )
        save_session(
            str(tmp_path),
            "two",
            [Message.system("system"), Message.user("Second task")],
            project_path="/tmp/two",
            project_name="Two",
            model="gpt-5.4",
            mode="plan",
        )

        all_sessions = list_sessions(str(tmp_path))
        filtered_sessions = list_sessions(str(tmp_path), project_path="/tmp/two")
        latest = load_latest_session(str(tmp_path))

        assert len(all_sessions) == 2
        assert len(filtered_sessions) == 1
        assert filtered_sessions[0].session_id == "two"
        assert latest is not None
