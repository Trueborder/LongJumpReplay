from src.timeline import choose_tick_step, format_relative


def test_tick_step_adapts_to_zoom():
    assert choose_tick_step(.5, 1000) <= .05
    assert choose_tick_step(40, 800) >= 5


def test_relative_time_format():
    assert format_relative(-1.234, True).startswith('−1.234')
    assert format_relative(65, False).startswith('+01:')
