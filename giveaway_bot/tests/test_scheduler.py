"""Планировщик публикаций (без реальной отправки в Telegram)."""
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from bot.utils import scheduler as sched


def test_safe_text_escapes_html():
    assert sched._safe_text("a & b") == "a &amp; b"
    assert sched._safe_text("x < y") == "x &lt; y"


@patch.object(sched, "bot")
@patch.object(sched, "GiveawayService")
def test_publish_giveaway_skips_when_already_published(mock_gs, mock_bot):
    mock_gs.get_giveaway.return_value = {"is_published": True}
    sched.publish_giveaway(1)
    mock_bot.send_message.assert_not_called()


@patch.object(sched, "bot")
@patch.object(sched, "GiveawayService")
def test_publish_giveaway_skips_without_channel(mock_gs, mock_bot):
    mock_gs.get_giveaway.return_value = {
        "id": 3,
        "is_published": False,
        "channel_id": None,
        "title": "T",
        "description": "D",
        "winners_count": 1,
        "end_time": datetime.utcnow(),
        "required_channels": [],
        "twitch_channels": [],
        "photo_file_id": None,
        "document_file_id": None,
    }
    sched.publish_giveaway(3)
    mock_bot.send_message.assert_not_called()


@patch.object(sched, "bot")
@patch.object(sched, "GiveawayService")
def test_finish_giveaway_skips_when_finished(mock_gs, mock_bot):
    mock_gs.get_giveaway.return_value = {"is_finished": True}
    sched.finish_giveaway(1)
    mock_bot.send_message.assert_not_called()


@patch.object(sched.scheduler, "get_job", return_value=None)
@patch.object(sched.scheduler, "add_job")
@patch.object(sched, "publish_giveaway")
def test_check_giveaways_schedules_future_publish(mock_pub, mock_add_job, _gj):
    now = datetime.utcnow()
    mock_gs_class = MagicMock()
    mock_gs_class.get_active_giveaways.return_value = [
        {"id": 10, "start_time": now + timedelta(hours=1)},
    ]
    mock_gs_class.get_finished_giveaways.return_value = []
    with patch.object(sched, "GiveawayService", mock_gs_class):
        sched.check_giveaways()
    mock_add_job.assert_called_once()
    mock_pub.assert_not_called()
