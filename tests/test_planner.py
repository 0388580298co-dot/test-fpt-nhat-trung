from openpilot.planner import create_plan


def test_create_plan():
    plan = create_plan("Analyze the project")
    assert plan.goal == "Analyze the project"
    assert len(plan.steps) == 4


def test_empty_goal_is_rejected():
    try:
        create_plan("   ")
    except ValueError:
        return
    raise AssertionError("Expected ValueError")
