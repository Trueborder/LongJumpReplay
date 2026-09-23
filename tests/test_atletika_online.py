from datetime import date

from src.atletika_online import parse_calendar_events, parse_jump_rosters


def test_calendar_parser_filters_the_selected_day_and_prefers_event_id() -> None:
    html = """
    <li class="results__row"><span class="results__date">15. 09. 2026</span>
      <span class="results__info"><strong>City jumps</strong><br>Praha, AC Test</span>
      <a href="/Propozice/propozice/123">Info</a><a href="/vysledky/123">Results</a></li>
    <li class="results__row"><span class="results__date">16. 09. 2026</span>
      <span class="results__info"><strong>Tomorrow</strong><br>Brno</span>
      <a href="/vysledky/456">Results</a></li>
    """
    events = parse_calendar_events(html, date(2026, 9, 15))
    assert [(item.event_id, item.name, item.place) for item in events] == [("123", "City jumps", "Praha, AC Test")]


def test_long_jump_parser_maps_categories_and_keeps_names_and_clubs() -> None:
    html = """
    <h2 class="main-result-header"><span class="disciplineName">skok daleký</span> - Ml. žáci</h2>
    <table><tbody><tr><td>1</td><td></td><td>
      <a class="resultsEanLink" href="/vysledky-atleta/2026/1001">Jan Novák</a>
      <span class="athleteclub noprint">AC Praha</span></td></tr></tbody></table>
    <h2 class="main-result-header"><span class="disciplineName">skok daleký</span> - Ml. žákyně</h2>
    <table><tbody><tr><td>1</td><td></td><td>
      <span class="resultsEanLink">Eva Nová</span>
      <span class="athleteclub noprint">SK Brno</span></td></tr></tbody></table>
    """
    rosters = parse_jump_rosters(html)
    assert [(item.group, item.label, len(item.athletes)) for item in rosters] == [
        ("Boys", "skok daleký - Ml. žáci", 1),
        ("Girls", "skok daleký - Ml. žákyně", 1),
    ]
    assert rosters[0].athletes[0].name == "Jan Novák"
    assert rosters[0].athletes[0].club == "AC Praha"
    assert rosters[0].athletes[0].external_id == "1001"