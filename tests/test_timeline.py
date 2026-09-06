from src.timeline import choose_tick_step, format_relative, format_timeline_span, format_wall_time_ns


def test_tick_step_adapts_to_zoom():
    assert choose_tick_step(.5, 1000) <= .05
    assert choose_tick_step(40, 800) >= 5


def test_relative_time_format():
    assert format_relative(-1.234, True).startswith('−1.234')
    assert format_relative(65, False).startswith('+01:')


def test_wall_clock_and_zoom_span_format():
    assert format_wall_time_ns(1_700_000_000_123_000_000).count(':') == 2
    assert format_wall_time_ns(1_700_000_000_123_000_000).endswith('.123')
    assert format_timeline_span(60) == '1.0 min view'
