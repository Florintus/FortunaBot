"""Каналы бота."""
from bot.services.channel_service import ChannelService


def test_add_update_remove_channel():
    ChannelService.add_channel("-1001", "First", "channel")
    all_c = ChannelService.get_all_channels()
    assert len(all_c) == 1
    assert all_c[0]["chat_id"] == "-1001"
    assert all_c[0]["title"] == "First"

    ChannelService.add_channel("-1001", "Updated", "group")
    all_c2 = ChannelService.get_all_channels()
    assert len(all_c2) == 1
    assert all_c2[0]["title"] == "Updated"
    assert all_c2[0]["chat_type"] == "group"

    ChannelService.remove_channel("-1001")
    assert ChannelService.get_all_channels() == []
