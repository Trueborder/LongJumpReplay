from src.shuttle_hid import jog_direction, parse_shuttle_packet


def test_shuttlexpress_packet_parser():
    # shuttle=-3, jog=255, buttons 1 and 5 for Xpress
    packet = bytes([0xFD, 0xFF, 0x00, 0x10, 0x01])
    shuttle, jog, buttons = parse_shuttle_packet(packet, 0x0020)
    assert shuttle == -3
    assert jog == 255
    assert buttons == [1, 5]


def test_report_id_is_accepted():
    shuttle, jog, buttons = parse_shuttle_packet(bytes([0, 2, 9, 0, 0x20, 0]), 0x0020)
    assert (shuttle, jog, buttons) == (2, 9, [2])


def test_jog_wrap_direction():
    assert jog_direction(255, 0) == 1
    assert jog_direction(0, 255) == -1
    assert jog_direction(10, 11) == 1
    assert jog_direction(11, 10) == -1
