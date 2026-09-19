from __future__ import annotations

from .cad_standards import (
    CriterionDefinition,
    CriterionRule,
    CriterionSource,
    StandardsProfile,
    build_standards_profile,
)


RP22_SOURCE_URI = (
    'https://cedia.org/site/assets/files/6057/'
    'cedia-cta_rp22_v1_2_sept_2023.pdf'
)
DOLBY_ATMOS_GUIDE_URI = (
    'https://www.dolby.com/siteassets/technologies/dolby-atmos/'
    'atmos-installation-guidelines-121318_r3.1.pdf'
)
AURO3D_HOME_GUIDE_URI = (
    'https://www.auro-3d.com/wp-content/uploads/2024/05/'
    'Auro-3D-Home-Theater-Setup-Guidelines-v12-20240516.pdf'
)


def _rp22_source(reference: str) -> CriterionSource:
    return CriterionSource(
        publisher='CEDIA / Consumer Technology Association (CTA)',
        document_title='CEDIA/CTA-RP22 Recommended Practice for Immersive Audio Design',
        document_version='v1.2, September 2023',
        reference=reference,
        source_uri=RP22_SOURCE_URI,
        note=(
            'Publicly available RP22 v1.2 source. This HTDT profile contains only '
            'the explicitly encoded spatial/layout subset; it is not an overall '
            'RP22 performance-level certification.'
        ),
    )


def _dolby_source(reference: str) -> CriterionSource:
    return CriterionSource(
        publisher='Dolby Laboratories',
        document_title='Dolby Atmos Home Theater Installation Guidelines',
        document_version='R3.1, 13 December 2018',
        reference=reference,
        source_uri=DOLBY_ATMOS_GUIDE_URI,
        note=(
            'Public Dolby installation guidance. HTDT evaluates only the explicit '
            'speaker-angle ranges encoded here; no additional tolerance is inferred.'
        ),
    )


def _auro3d_source(reference: str) -> CriterionSource:
    return CriterionSource(
        publisher='NEWAURO BV',
        document_title='AURO-3D Home Theater Setup — Installation Guidelines',
        document_version='Rev. 12, 16 May 2024',
        reference=reference,
        source_uri=AURO3D_HOME_GUIDE_URI,
        note=(
            'Public AURO-3D home-theater guidance. HTDT encodes only explicit '
            'normative min/max or minimum-angle criteria from the cited sections.'
        ),
    )


_RP22_LISTENER_WALL_MIN_M = {
    1: 0.5,
    2: 0.8,
    3: 1.2,
    4: 1.5,
}
_RP22_MAX_HORIZONTAL_ADJACENT_DEG = {
    2: 80.0,
    3: 60.0,
    4: 50.0,
}
_RP22_WIDE_DEVIATION_MAX_DEG = {
    1: 10.0,
    2: 7.0,
    3: 5.0,
    4: 2.0,
}
_RP22_MAX_VERTICAL_ADJACENT_DEG = {
    2: 80.0,
    3: 60.0,
    4: 50.0,
}


def rp22_spatial_profile(level: int) -> StandardsProfile:
    """Return the explicit spatial/layout subset for one RP22 performance level.

    This deliberately excludes SPL/headroom, acoustic-response, and other RP22
    criteria that belong to separate physical/evidence authorities.
    """

    if level not in {1, 2, 3, 4}:
        raise ValueError('RP22 performance level must be 1, 2, 3, or 4')

    criteria: list[CriterionDefinition] = [
        CriterionDefinition(
            criterion_id='rp22.p01.listener-boundary-distance',
            name='Minimum listener-to-boundary distance',
            source=_rp22_source('Appendix A, Parameter 1; §4.1.4'),
            quantity='listener_head_to_nearest_room_boundary',
            unit='m',
            applicable_domains=('seat',),
            required_inputs=('listener_head_to_nearest_room_boundary_m',),
            required_capabilities=('scene-geometry-distance-v1',),
            rule=CriterionRule(
                operator='min',
                minimum=_RP22_LISTENER_WALL_MIN_M[level],
                lower_inclusive=False,
            ),
            note='RP22 Appendix A uses a strict greater-than boundary for Parameter 1.',
        ),
        CriterionDefinition(
            criterion_id='rp22.p03.screen-speakers-outside-zone-count',
            name='Screen-wall speakers outside recommended zonal locations',
            source=_rp22_source('Appendix A, Parameter 3; §5.5.4'),
            quantity='screen_wall_speakers_outside_recommended_zone_count',
            unit='count',
            applicable_domains=('room', 'speaker_layout'),
            required_inputs=('screen_wall_speakers_outside_recommended_zone_count',),
            required_capabilities=('rp22-recommended-zone-evaluation-v1',),
            rule=CriterionRule(operator='max', maximum=0.0),
        ),
        CriterionDefinition(
            criterion_id='rp22.p07.wide-horizontal-median-deviation',
            name='Wide-speaker horizontal deviation from median angle',
            source=_rp22_source('Appendix A, Parameter 7; §5.7'),
            quantity='wide_horizontal_angle_deviation_from_median',
            unit='deg',
            applicable_domains=('wide_speaker',),
            required_inputs=('wide_horizontal_deviation_from_median_deg',),
            required_capabilities=('layout-angle-v1',),
            rule=CriterionRule(
                operator='max',
                maximum=_RP22_WIDE_DEVIATION_MAX_DEG[level],
                angle_wrap='signed_180',
                absolute_value=True,
            ),
        ),
    ]

    if level in _RP22_MAX_HORIZONTAL_ADJACENT_DEG:
        criteria.append(
            CriterionDefinition(
                criterion_id='rp22.p05.max-adjacent-surround-horizontal-angle',
                name='Maximum horizontal angle between adjacent surround speakers',
                source=_rp22_source('Appendix A, Parameter 5; §5.6.2.1'),
                quantity='adjacent_surround_speaker_horizontal_angle',
                unit='deg',
                applicable_domains=('seat', 'speaker_layout'),
                required_inputs=('max_adjacent_surround_horizontal_angle_deg',),
                required_capabilities=('layout-angle-v1',),
                rule=CriterionRule(
                    operator='max',
                    maximum=_RP22_MAX_HORIZONTAL_ADJACENT_DEG[level],
                ),
            )
        )
        criteria.append(
            CriterionDefinition(
                criterion_id='rp22.p09.max-adjacent-upper-vertical-angle',
                name='Maximum vertical angle between adjacent upper speakers',
                source=_rp22_source('Appendix A, Parameter 9; §5.8.2'),
                quantity='adjacent_upper_speaker_vertical_angle',
                unit='deg',
                applicable_domains=('seat', 'speaker_layout'),
                required_inputs=('max_adjacent_upper_vertical_angle_deg',),
                required_capabilities=('layout-angle-v1',),
                rule=CriterionRule(
                    operator='max',
                    maximum=_RP22_MAX_VERTICAL_ADJACENT_DEG[level],
                ),
            )
        )
        criteria.append(
            CriterionDefinition(
                criterion_id='rp22.p11.surround-wide-upper-outside-zone-count',
                name='Surround, wide, and upper speakers outside recommended zones',
                source=_rp22_source('Appendix A, Parameter 11; §5.9.3'),
                quantity='surround_wide_upper_speakers_outside_recommended_zone_count',
                unit='count',
                applicable_domains=('room', 'speaker_layout'),
                required_inputs=(
                    'surround_wide_upper_speakers_outside_recommended_zone_count',
                ),
                required_capabilities=('rp22-recommended-zone-evaluation-v1',),
                rule=CriterionRule(operator='max', maximum=0.0),
            )
        )

    if level >= 3:
        criteria.append(
            CriterionDefinition(
                criterion_id='rp22.p08.upfiring-elevation-speakers-prohibited',
                name='Up-firing elevation speakers prohibited',
                source=_rp22_source('Appendix A, Parameter 8; §5.8.2'),
                quantity='uses_upfiring_elevation_speakers',
                unit='boolean',
                applicable_domains=('room', 'speaker_layout'),
                required_inputs=('uses_upfiring_elevation_speakers',),
                required_capabilities=('speaker-rendering-mode-v1',),
                rule=CriterionRule(operator='equals', expected=False),
                note=(
                    'Only Levels 3 and 4 are encoded: the source explicitly disallows '
                    'up-firing/elevation speakers there. Levels 1 and 2 say they are '
                    'allowed, which is not treated as a requirement to use them.'
                ),
            )
        )

    return build_standards_profile(
        profile_id=f'cedia-cta-rp22-spatial-level-{level}',
        version='1.2-2023-09',
        name=f'CEDIA/CTA RP22 v1.2 spatial/layout subset — Level {level}',
        profile_kind='published',
        criteria=criteria,
    )


def dolby_atmos_home_5_1_2_profile() -> StandardsProfile:
    """Public Dolby 5.1.2 azimuth ranges mapped to HTDT signed azimuth.\n\n    HTDT uses 0 degrees toward the screen/front, positive toward +X/right,\n    negative toward -X/left, normalized to [-180, 180).\n    """

    criteria = (
        CriterionDefinition(
            criterion_id='dolby.5.1.2.front-left-azimuth',
            name='Front-left speaker azimuth',
            source=_dolby_source('Figure 12, page 28 — 5.1.2 speaker placement'),
            quantity='speaker_azimuth_from_mlp',
            unit='deg',
            applicable_domains=('speaker_layout',),
            required_inputs=('front_left_azimuth_deg',),
            required_capabilities=('layout-angle-v1',),
            rule=CriterionRule(
                operator='range',
                minimum=-30.0,
                maximum=-22.0,
                angle_wrap='signed_180',
            ),
        ),
        CriterionDefinition(
            criterion_id='dolby.5.1.2.front-right-azimuth',
            name='Front-right speaker azimuth',
            source=_dolby_source('Figure 12, page 28 — 5.1.2 speaker placement'),
            quantity='speaker_azimuth_from_mlp',
            unit='deg',
            applicable_domains=('speaker_layout',),
            required_inputs=('front_right_azimuth_deg',),
            required_capabilities=('layout-angle-v1',),
            rule=CriterionRule(
                operator='range',
                minimum=22.0,
                maximum=30.0,
                angle_wrap='signed_180',
            ),
        ),
        CriterionDefinition(
            criterion_id='dolby.5.1.2.surround-left-azimuth',
            name='Surround-left speaker azimuth',
            source=_dolby_source('Figure 12, page 28 — 5.1.2 speaker placement'),
            quantity='speaker_azimuth_from_mlp',
            unit='deg',
            applicable_domains=('speaker_layout',),
            required_inputs=('surround_left_azimuth_deg',),
            required_capabilities=('layout-angle-v1',),
            rule=CriterionRule(
                operator='range',
                minimum=-110.0,
                maximum=-90.0,
                angle_wrap='signed_180',
            ),
        ),
        CriterionDefinition(
            criterion_id='dolby.5.1.2.surround-right-azimuth',
            name='Surround-right speaker azimuth',
            source=_dolby_source('Figure 12, page 28 — 5.1.2 speaker placement'),
            quantity='speaker_azimuth_from_mlp',
            unit='deg',
            applicable_domains=('speaker_layout',),
            required_inputs=('surround_right_azimuth_deg',),
            required_capabilities=('layout-angle-v1',),
            rule=CriterionRule(
                operator='range',
                minimum=90.0,
                maximum=110.0,
                angle_wrap='signed_180',
            ),
        ),
    )
    return build_standards_profile(
        profile_id='dolby-atmos-home-5.1.2-layout',
        version='r3.1-2018-12-13',
        name='Dolby Atmos Home Theater 5.1.2 layout guidance',
        profile_kind='published',
        criteria=criteria,
    )


def auro3d_home_v12_profile() -> StandardsProfile:
    """Explicit public AURO-3D Rev.12 elevation/opening-angle criteria.

    Table 3 is titled "Normative Speaker Positions". This profile deliberately
    avoids horizontal azimuth rows whose published table contains an apparent
    sign inconsistency for Height Right; HTDT does not silently repair source data.
    """

    criteria = (
        CriterionDefinition(
            criterion_id='auro.v12.lower-layer-max-elevation',
            name='Maximum lower-layer speaker elevation',
            source=_auro3d_source('§3.3.1.1 and Table 3, page 26'),
            quantity='speaker_elevation_from_mlp',
            unit='deg',
            applicable_domains=('auro_lower_speaker',),
            required_inputs=('lower_layer_speaker_elevation_deg',),
            required_capabilities=('layout-angle-v1',),
            rule=CriterionRule(operator='max', maximum=10.0),
            note=(
                'The source states the Surround layer should not exceed 10° and '
                'Table 3 gives 10° as the maximum elevation for lower-layer roles. '
                'No unstated lower bound is inferred.'
            ),
        ),
        CriterionDefinition(
            criterion_id='auro.v12.height-layer-elevation',
            name='Height-layer speaker elevation',
            source=_auro3d_source('Table 3, page 26 — Normative Speaker Positions'),
            quantity='speaker_elevation_from_mlp',
            unit='deg',
            applicable_domains=('auro_height_speaker',),
            required_inputs=('height_layer_speaker_elevation_deg',),
            required_capabilities=('layout-angle-v1',),
            rule=CriterionRule(
                operator='range',
                minimum=25.0,
                maximum=40.0,
            ),
        ),
        CriterionDefinition(
            criterion_id='auro.v12.top-speaker-elevation',
            name='Top speaker elevation',
            source=_auro3d_source('Table 3, page 26 — Normative Speaker Positions'),
            quantity='speaker_elevation_from_mlp',
            unit='deg',
            applicable_domains=('auro_top_speaker',),
            required_inputs=('top_speaker_elevation_deg',),
            required_capabilities=('layout-angle-v1',),
            rule=CriterionRule(
                operator='range',
                minimum=65.0,
                maximum=100.0,
            ),
        ),
        CriterionDefinition(
            criterion_id='auro.v12.surround-height-opening-angle',
            name='Minimum opening angle between Surround and Height layers',
            source=_auro3d_source('§3.3.1.1 and Table 3 note, pages 24 and 26'),
            quantity='surround_to_height_opening_angle',
            unit='deg',
            applicable_domains=('speaker_layout',),
            required_inputs=('surround_height_opening_angle_deg',),
            required_capabilities=('layout-angle-v1',),
            rule=CriterionRule(operator='min', minimum=25.0),
        ),
        CriterionDefinition(
            criterion_id='auro.v12.screen-height-opening-angle',
            name='Minimum opening angle for Height screen channels',
            source=_auro3d_source('Table 3 note, page 26'),
            quantity='screen_to_height_opening_angle',
            unit='deg',
            applicable_domains=('speaker_layout',),
            required_inputs=('screen_height_opening_angle_deg',),
            required_capabilities=('layout-angle-v1',),
            rule=CriterionRule(operator='min', minimum=22.0),
        ),
    )
    return build_standards_profile(
        profile_id='auro3d-home-layout',
        version='rev12-2024-05-16',
        name='AURO-3D Home Theater Setup Rev.12 explicit layout criteria',
        profile_kind='published',
        criteria=criteria,
    )


def builtin_standards_profiles() -> tuple[StandardsProfile, ...]:
    """Profiles whose pass/fail boundaries are explicit in public source material."""

    return (
        rp22_spatial_profile(1),
        rp22_spatial_profile(2),
        rp22_spatial_profile(3),
        rp22_spatial_profile(4),
        dolby_atmos_home_5_1_2_profile(),
        auro3d_home_v12_profile(),
    )
