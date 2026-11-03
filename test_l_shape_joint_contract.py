"""Issue #2: check complete physical rods, not intersections split after the fact."""
from __future__ import annotations

from collections import defaultdict
from math import atan2, degrees

from shapely.geometry import LineString, Point
import pytest
import ezdxf

from main_strut import export_strut_dxf
import strut_diagnostics
from strut_engine import StrutEngine
from strut_validation import validate_concave_web_rods
from test_strut_minimal import L_SHAPE_COORDS, _l_shape_layout, _logical_members


def test_edge_web_is_one_waling_to_chord_rod_without_support_crossing() -> None:
    layout = _l_shape_layout()
    members = _logical_members(layout['members'])
    waling = LineString(layout['waling'])
    supports = [m for m in members if m['kind'] == 'main_strut'
                or m.get('support_role') == 'reentrant_opposite_strut']
    for web in members:
        if web.get('edge_role') != 'web':
            continue
        line = LineString(web['geometry'])
        ends = [Point(line.coords[0]), Point(line.coords[-1])]
        assert sum(waling.distance(p) < 1e-5 for p in ends) == 1
        for support in supports:
            crossing = line.intersection(LineString(support['geometry']))
            if crossing.is_empty:
                continue
            assert crossing.geom_type == 'Point', (web, support)
            assert min(crossing.distance(p) for p in ends) < 1e-5, (web, support)


def test_regular_opposite_struts_are_explicit_two_rod_groups() -> None:
    members = _logical_members(_l_shape_layout()['members'])
    ordinary = [m for m in members if m['kind'] == 'main_strut' and not m.get('conversion_group')]
    assert ordinary
    groups = defaultdict(list)
    for member in ordinary:
        assert member.get('opposite_pair_id'), member
        groups[member['opposite_pair_id']].append(member)
    gaps = []
    for group in groups.values():
        assert len(group) == 2
        left, right = [LineString(m['geometry']) for m in group]
        gaps.append(left.distance(right))
        assert left.intersection(right).is_empty
    assert max(gaps) - min(gaps) < 1e-5
    assert len(groups) == 3  # two vertical fields and one bottom-arm horizontal field


def test_edge_web_coverage_has_no_deleted_panel_bays() -> None:
    layout = _l_shape_layout()
    members = _logical_members(layout['members'])
    for index, (a, b) in enumerate(zip(layout['waling'], layout['waling'][1:]), 1):
        edge = LineString([a, b])
        spans = []
        for web in members:
            if web.get('edge_role') != 'web' or web.get('edge_truss_id') != f'edge_truss_{index}':
                continue
            spans.append(sorted(edge.project(Point(p)) for p in (web['geometry'][0], web['geometry'][-1])))
        assert spans
        spans.sort()
        cursor = spans[0][0]
        for start, end in spans:
            assert start <= cursor + 1e-5, (index, cursor, start)
            cursor = max(cursor, end)
        def corner_reach(corner_index: int) -> float:
            tiers = [m['tier_index'] for m in members
                     if m.get('belongs_to_corner_bracket') == f'corner_bracket_{corner_index}'
                     and m.get('truss_primitive') == 'corner_tier']
            return 4.5 * max(tiers, default=2)

        assert abs(spans[0][0] - corner_reach(index)) < 1e-5
        next_corner = index % (len(layout['waling']) - 1) + 1
        assert abs(cursor - (edge.length - corner_reach(next_corner))) < 1e-5


def test_support_chord_joint_is_tip_of_two_diagonal_waling_rods() -> None:
    layout = _l_shape_layout()
    members = _logical_members(layout['members'])
    for index, (a, b) in enumerate(zip(layout['waling'], layout['waling'][1:]), 1):
        edge = LineString([a, b])
        edge_id = f'edge_truss_{index}'
        chord = next(LineString(m['geometry']) for m in members
                     if m.get('edge_truss_id') == edge_id and m.get('edge_role') == 'inner_chord')
        webs = [LineString(m['geometry']) for m in members
                if m.get('edge_truss_id') == edge_id and m.get('edge_role') == 'web']
        for main in members:
            if main['kind'] != 'main_strut':
                continue
            joint = chord.intersection(LineString(main['geometry']))
            if joint.geom_type != 'Point' or not 9.0 + 1e-5 < edge.project(joint) < edge.length - 9.0 - 1e-5:
                continue
            arms = [line for line in webs if min(joint.distance(Point(p))
                    for p in (line.coords[0], line.coords[-1])) < 1e-5]
            assert len(arms) == 2, (edge_id, joint.wkt)
            outer_stations = [edge.project(Point(p)) for line in arms for p in line.coords
                              if edge.distance(Point(p)) < 1e-5]
            assert min(outer_stations) < edge.project(joint) < max(outer_stations)
            axis = LineString(main['geometry'])
            for arm in arms:
                far = max((Point(p) for p in arm.coords), key=lambda p: p.distance(joint))
                dx, dy = far.x - joint.x, far.y - joint.y
                angle = degrees(atan2(abs(dy), abs(dx)))
                to_support = angle if abs(axis.coords[0][1] - axis.coords[-1][1]) < 1e-5 else 90 - angle
                assert to_support >= 20.0 - 1e-5, (edge_id, joint.wkt, to_support)


def test_short_right_edge_uses_one_corner_tier_when_double_struts_need_room() -> None:
    layout = _l_shape_layout()
    for i, corner in enumerate(layout['waling'][:-1], 1):
        if abs(corner[0] - 62.0) > 1e-5:
            continue
        roles = {member.get('corner_role') for member in layout['members']
                 if member.get('belongs_to_corner_bracket') == f'corner_bracket_{i}'}
        assert 'tier_1' in roles
        assert 'tier_2' not in roles


def test_validator_rejects_a_web_crossing_even_when_split_at_the_crossing() -> None:
    layout = {
        'waling': L_SHAPE_COORDS + [L_SHAPE_COORDS[0]],
        'members': [
            {'id': 'web1', 'parent_member_id': 'web', 'kind': 'truss_web',
             'system': 'brace', 'edge_role': 'web', 'edge_truss_id': 'edge',
             'geometry': [(10, 40), (12, 39)], 'logical_geometry': [(10, 40), (14, 38)]},
            {'id': 'main', 'kind': 'main_strut', 'system': 'brace',
             'geometry': [(12, 0), (12, 40)]},
            {'id': 'chord', 'kind': 'truss_chord', 'system': 'brace',
             'edge_role': 'inner_chord', 'edge_truss_id': 'edge',
             'geometry': [(0, 38), (30, 38)]},
        ],
    }
    issues = validate_concave_web_rods(layout)
    assert any(issue.reason == 'logical_web_crosses_member' and issue.other_member_id == 'main'
               for issue in issues)


def test_transfer_inner_chords_share_strut_visual_marking_and_keep_dxf_layer(tmp_path) -> None:
    layout = _l_shape_layout()
    chord = next(m for m in layout['members'] if m['kind'] == 'truss_chord'
                 and m.get('support_role') == 'reentrant_opposite_strut')
    main = next(m for m in layout['members'] if m['kind'] == 'main_strut'
                and m.get('support_role') == 'reentrant_opposite_strut')
    assert hasattr(strut_diagnostics, '_member_style')
    assert strut_diagnostics._member_style(chord)['color'] == strut_diagnostics._member_style(main)['color']
    path = tmp_path / 'support.dxf'
    export_strut_dxf(path, L_SHAPE_COORDS, layout)
    doc = ezdxf.readfile(path)
    expected = LineString(chord['geometry'])
    matching = [entity for entity in doc.modelspace().query('LWPOLYLINE[layer=="TRUSS_CHORD"]')
                if len(entity) == 2 and LineString([(p[0], p[1]) for p in entity.get_points()])
                .equals_exact(expected, 1e-5)]
    assert matching and matching[0].dxf.color == doc.layers.get('STRUT').dxf.color


@pytest.mark.parametrize('coords', [
    list(reversed(L_SHAPE_COORDS)),
    [(x + 71, y - 23) for x, y in L_SHAPE_COORDS],
    [(-x, y) for x, y in L_SHAPE_COORDS],
    [(y, x) for x, y in L_SHAPE_COORDS],
    [(-y, x) for x, y in L_SHAPE_COORDS],
])
def test_node_driven_l_shape_is_coordinate_and_winding_independent(coords) -> None:
    layout = StrutEngine(coords, {'support_system': 'brace', 'spacing': 9.0,
                                 'waling_offset': 2.0, 'safe_dist': 1.5}).solve()
    assert not [issue for issue in layout['issues'] if issue['severity'] == 'error']
    assert not validate_concave_web_rods(layout)
    pairs = defaultdict(list)
    for m in _logical_members(layout['members']):
        if m['kind'] == 'main_strut' and not m.get('conversion_group'):
            pairs[m.get('opposite_pair_id')].append(m)
    assert None not in pairs
    assert len(pairs) == 3
    assert all(len(members) == 2 for members in pairs.values())
