"""Сервис розыгрышей на SQLite."""
from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from bot.services.giveaway_service import GiveawayService


def _sample_giveaway_payload(**kwargs):
    now = datetime.utcnow()
    base = {
        "creator_id": 1001,
        "title": "Призы",
        "description": "Описание",
        "start_time": now,
        "end_time": now + timedelta(hours=2),
        "required_channels": ["@channel_one"],
        "twitch_channels": ["https://twitch.tv/foo"],
        "winners_count": 2,
        "channel_id": "-100123456",
    }
    base.update(kwargs)
    return base


def test_create_and_get_giveaway():
    g = GiveawayService.create_giveaway(_sample_giveaway_payload())
    assert g["id"] is not None
    assert g["participants_count"] == 0
    loaded = GiveawayService.get_giveaway(g["id"])
    assert loaded["title"] == "Призы"
    assert loaded["required_channels"] == ["@channel_one"]


def test_create_giveaway_accepts_json_string_lists():
    """Как из FSM, если каналы пришли строкой JSON — преобразуем в list."""
    now = datetime.utcnow()
    g = GiveawayService.create_giveaway(
        {
            "creator_id": 1,
            "title": "T",
            "description": "D",
            "start_time": now,
            "end_time": now + timedelta(hours=1),
            "required_channels": '["@a"]',
            "twitch_channels": "[]",
            "winners_count": 1,
            "channel_id": "@ch",
        }
    )
    loaded = GiveawayService.get_giveaway(g["id"])
    assert loaded["required_channels"] == ["@a"]
    assert loaded["twitch_channels"] == []


def test_add_participant_once():
    g = GiveawayService.create_giveaway(_sample_giveaway_payload())
    gid = g["id"]
    assert GiveawayService.add_participant(gid, 42, "u1", "User One") is True
    assert GiveawayService.add_participant(gid, 42, "u1", "User One") is False
    assert GiveawayService.is_participant(gid, 42) is True


def test_select_winners_marks_finished_and_empty():
    g = GiveawayService.create_giveaway(_sample_giveaway_payload(winners_count=1))
    gid = g["id"]
    winners = GiveawayService.select_winners(gid)
    assert winners == []
    again = GiveawayService.get_giveaway(gid)
    assert again["is_finished"] is True


def test_select_winners_picks_sample():
    g = GiveawayService.create_giveaway(_sample_giveaway_payload(winners_count=2))
    gid = g["id"]
    GiveawayService.add_participant(gid, 1, "a", "A")
    GiveawayService.add_participant(gid, 2, "b", "B")
    GiveawayService.add_participant(gid, 3, "c", "C")

    class _Participant:
        def __init__(self, user_id, username, full_name):
            self.user_id = user_id
            self.username = username
            self.full_name = full_name

    fake = [_Participant(1, "a", "A"), _Participant(2, "b", "B")]
    with patch("bot.services.giveaway_service.random.sample", return_value=fake):
        winners = GiveawayService.select_winners(gid)
    assert len(winners) == 2
    assert {w["user_id"] for w in winners} == {1, 2}
    assert GiveawayService.get_giveaway(gid)["is_finished"] is True


def test_delete_giveaway_only_owner():
    g = GiveawayService.create_giveaway(_sample_giveaway_payload(creator_id=7))
    gid = g["id"]
    assert GiveawayService.delete_giveaway(gid, 999) is False
    assert GiveawayService.delete_giveaway(gid, 7) is True
    assert GiveawayService.get_giveaway(gid) is None


def test_get_active_and_finished_lists():
    now = datetime.utcnow()
    GiveawayService.create_giveaway(
        _sample_giveaway_payload(
            is_published=False,
            is_finished=False,
            start_time=now + timedelta(days=1),
        )
    )
    GiveawayService.create_giveaway(
        _sample_giveaway_payload(
            is_published=True,
            is_finished=False,
            start_time=now - timedelta(hours=1),
            end_time=now + timedelta(hours=1),
        )
    )
    active = GiveawayService.get_active_giveaways()
    finished_window = GiveawayService.get_finished_giveaways()
    assert len(active) == 1
    assert active[0]["is_published"] is False
    assert len(finished_window) == 1
    assert finished_window[0]["is_published"] is True


def test_update_message_id_and_mark_published():
    g = GiveawayService.create_giveaway(_sample_giveaway_payload())
    gid = g["id"]
    GiveawayService.update_message_id(gid, 555)
    g2 = GiveawayService.get_giveaway(gid)
    assert g2["message_id"] == 555
    assert g2["is_published"] is True


def test_get_user_giveaways_order():
    GiveawayService.create_giveaway(_sample_giveaway_payload(creator_id=1, title="Old"))
    GiveawayService.create_giveaway(_sample_giveaway_payload(creator_id=1, title="New"))
    rows = GiveawayService.get_user_giveaways(1)
    assert [r["title"] for r in rows] == ["New", "Old"]
