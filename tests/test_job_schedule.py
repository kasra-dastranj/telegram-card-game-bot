from unittest.mock import Mock

from bot.main import MAINTENANCE_TIMEZONE, PANEL_TIMEOUT, schedule_maintenance_jobs


def test_interactive_panels_expire_after_one_minute():
    assert PANEL_TIMEOUT == 60


def test_maintenance_jobs_do_not_run_daily_or_weekly_tasks_on_startup():
    job_queue = Mock()
    bot = Mock()

    schedule_maintenance_jobs(job_queue, bot)

    job_queue.run_repeating.assert_called_once_with(
        bot.cleanup_task,
        interval=3600,
        first=10,
        name="hourly-cleanup",
    )

    daily_calls = job_queue.run_daily.call_args_list
    assert len(daily_calls) == 3

    reset_call, decay_call, weekly_call = daily_calls
    assert reset_call.args == (bot.reset_lives_task,)
    assert reset_call.kwargs["time"].hour == 0
    assert reset_call.kwargs["time"].minute == 5
    assert reset_call.kwargs["time"].tzinfo is MAINTENANCE_TIMEZONE
    assert "first" not in reset_call.kwargs

    assert decay_call.args == (bot.tier_decay_task,)
    assert decay_call.kwargs["time"].hour == 0
    assert decay_call.kwargs["time"].minute == 10
    assert "first" not in decay_call.kwargs

    assert weekly_call.args == (bot.weekly_leaderboard_task,)
    assert weekly_call.kwargs["time"].hour == 0
    assert weekly_call.kwargs["time"].minute == 15
    assert weekly_call.kwargs["days"] == (1,)
    assert "first" not in weekly_call.kwargs
