from __future__ import annotations

from hashlib import sha256
from pathlib import Path

import pytest

from htdt.cad_measurement_models import CadFrequencyResponseDataset
from htdt.cad_measurement_quality import (
    CadAcquisitionContextBinding,
    CadMeasurementQualityEvidence,
    build_measurement_lineage,
    build_measurement_quality_profile,
    build_measurement_quality_report,
)
from htdt.cad_measurement_quality_repository import CadMeasurementQualityRepository
from htdt.cad_measurement_repository import CadMeasurementRepository
from htdt.cad_measurements import measurement_record_for_revision
from htdt.cad_repository import SceneRepository
from htdt.cad_scene import make_f1_scene


def _repositories(tmp_path: Path):
    scene_repository = SceneRepository(tmp_path / 'cad.sqlite3')
    revision = scene_repository.save(make_f1_scene(), parent_revision_id=None).revision
    measurement_repository = CadMeasurementRepository(scene_repository)
    quality_repository = CadMeasurementQualityRepository(measurement_repository)
    return revision, measurement_repository, quality_repository


def _save_measurement(
    repository: CadMeasurementRepository,
    revision,
    measurement_id: str,
    *,
    raw: bytes,
    phase_status: str = 'absent',
    phase_deg: tuple[float, ...] | None = None,
    level_reference: str = 'unknown',
):
    record = measurement_record_for_revision(
        revision,
        'point-mlp',
        measurement_id=measurement_id,
        evidence_type='measured',
        channel_role='front_left',
        source_speaker_ids=('speaker-fl',),
        radiation_scope='single',
        routing_evidence='verified',
        imported_at='2026-09-19T00:00:00+00:00',
        source_kind='rew_api',
        external_source_id=f'rew-{measurement_id}',
    )
    dataset = CadFrequencyResponseDataset(
        dataset_id=f'dataset-{measurement_id}',
        measurement_id=measurement_id,
        frequency_hz=(20.0, 40.0, 80.0),
        level_db=(70.0, 71.0, 69.0),
        phase_deg=phase_deg,
        phase_status=phase_status,
        level_reference=level_reference,
        source_sha256=sha256(raw).hexdigest(),
        importer_version='fixture-1',
    )
    repository.save(
        record,
        dataset,
        raw_filename=f'{measurement_id}.json',
        raw_bytes=raw,
    )
    return record, dataset


def test_fr_only_quality_keeps_magnitude_and_does_not_invent_missing_evidence(tmp_path: Path) -> None:
    revision, measurement_repository, quality_repository = _repositories(tmp_path)
    record, dataset = _save_measurement(
        measurement_repository,
        revision,
        'fr-only',
        raw=b'fr-only',
    )
    profile = build_measurement_quality_profile()
    report = build_measurement_quality_report(
        measurement=record,
        dataset=dataset,
        evidence=CadMeasurementQualityEvidence(),
        profile=profile,
        report_id='report-fr-only',
        created_at_utc='2026-09-19T00:01:00+00:00',
    )

    assert report.clipping.status == 'UNKNOWN'
    assert report.noise_snr.status == 'UNKNOWN'
    assert report.usable_frequency_band.status == 'UNKNOWN'
    assert report.ir_window.status == 'NOT_EVALUATED'
    assert report.calibration.status == 'UNKNOWN'
    assert report.retake_recommendation == 'UNKNOWN'
    assert report.capability('magnitude_response').decision == 'ALLOWED'
    assert report.capability('phase_response').decision == 'BLOCKED'
    assert report.capability('common_timing').decision == 'UNKNOWN'
    assert report.capability('arrival_time').decision == 'BLOCKED'
    assert report.capability('decay').decision == 'BLOCKED'

    quality_repository.save_report(report)
    assert quality_repository.get_report(report.report_id) == report


def test_phase_array_does_not_imply_common_timing(tmp_path: Path) -> None:
    revision, measurement_repository, quality_repository = _repositories(tmp_path)
    record, dataset = _save_measurement(
        measurement_repository,
        revision,
        'phase-no-timing',
        raw=b'phase-no-timing',
        phase_status='valid',
        phase_deg=(5.0, 10.0, 15.0),
    )
    report = build_measurement_quality_report(
        measurement=record,
        dataset=dataset,
        evidence=CadMeasurementQualityEvidence(),
        profile=build_measurement_quality_profile(),
        report_id='report-phase-no-timing',
        created_at_utc='2026-09-19T00:02:00+00:00',
    )

    assert report.capability('phase_response').decision == 'ALLOWED'
    assert report.timing_reference.status == 'UNKNOWN'
    assert report.capability('common_timing').decision == 'UNKNOWN'
    assert report.capability('arrival_time').decision == 'BLOCKED'

    quality_repository.save_report(report)


def test_explicit_quality_metadata_opens_only_supported_claims(tmp_path: Path) -> None:
    revision, measurement_repository, quality_repository = _repositories(tmp_path)
    first, _ = _save_measurement(
        measurement_repository,
        revision,
        'repeat-a',
        raw=b'repeat-a',
        phase_status='valid',
        phase_deg=(5.0, 10.0, 15.0),
        level_reference='spl',
    )
    record, dataset = _save_measurement(
        measurement_repository,
        revision,
        'repeat-b',
        raw=b'repeat-b',
        phase_status='valid',
        phase_deg=(6.0, 11.0, 16.0),
        level_reference='spl',
    )
    calibration_sha = sha256(b'umik-calibration').hexdigest()
    acquisition = CadAcquisitionContextBinding(
        acquisition_context_id='acq-1',
        acquisition_context_sha256=sha256(b'acq-1').hexdigest(),
        source_kind='native',
    )
    evidence = CadMeasurementQualityEvidence(
        clipping_detected=False,
        peak_dbfs=-3.0,
        noise_floor_db_spl=30.0,
        signal_level_db_spl=70.0,
        snr_db=40.0,
        usable_frequency_band_hz=(20.0, 80.0),
        timing_reference_valid=True,
        timing_reference_id='loopback-1',
        clock_source='umik-1-usb',
        sample_rate_hz=48000,
        delay_correction_s=0.00025,
        polarity_correct=True,
        polarity_confidence=0.99,
        has_impulse_response=True,
        ir_window_start_s=-0.01,
        ir_window_end_s=0.5,
        ir_truncated=False,
        calibration_filename='umik.txt',
        calibration_file_sha256=calibration_sha,
        expected_calibration_file_sha256=calibration_sha,
        repeat_measurement_ids=(first.measurement_id, record.measurement_id),
        repeatability_rms_db=0.25,
        evidence_source='rew_metadata',
    )
    profile = build_measurement_quality_profile(
        required_usable_band_hz=(20.0, 80.0),
        minimum_snr_db=20.0,
        maximum_repeatability_rms_db=1.0,
    )
    report = build_measurement_quality_report(
        measurement=record,
        dataset=dataset,
        evidence=evidence,
        profile=profile,
        acquisition_context=acquisition,
        report_id='report-rich',
        created_at_utc='2026-09-19T00:03:00+00:00',
    )

    assert {
        report.clipping.status,
        report.noise_snr.status,
        report.usable_frequency_band.status,
        report.timing_reference.status,
        report.polarity.status,
        report.ir_window.status,
        report.calibration.status,
        report.repeatability.status,
    } == {'PASS'}
    assert report.retake_recommendation == 'NOT_NEEDED'
    assert all(item.decision == 'ALLOWED' for item in report.capabilities)

    quality_repository.save_report(report)
    assert quality_repository.latest_report(record.measurement_id) == report

    tampered = report.model_copy(update={'measurement_sha256': '0' * 64})
    with pytest.raises(ValueError, match='measurement hash mismatch'):
        quality_repository.save_report(tampered)


def test_calibration_file_mismatch_blocks_calibrated_claim_and_recommends_retake(tmp_path: Path) -> None:
    revision, measurement_repository, quality_repository = _repositories(tmp_path)
    record, dataset = _save_measurement(
        measurement_repository,
        revision,
        'cal-mismatch',
        raw=b'cal-mismatch',
    )
    acquisition = CadAcquisitionContextBinding(
        acquisition_context_id='acq-cal',
        acquisition_context_sha256=sha256(b'acq-cal').hexdigest(),
    )
    report = build_measurement_quality_report(
        measurement=record,
        dataset=dataset,
        evidence=CadMeasurementQualityEvidence(
            calibration_filename='wrong.txt',
            calibration_file_sha256=sha256(b'wrong-cal').hexdigest(),
            expected_calibration_file_sha256=sha256(b'expected-cal').hexdigest(),
        ),
        profile=build_measurement_quality_profile(),
        acquisition_context=acquisition,
        report_id='report-cal-mismatch',
        created_at_utc='2026-09-19T00:04:00+00:00',
    )

    assert report.calibration.status == 'FAIL'
    assert report.capability('calibrated_response').decision == 'BLOCKED'
    assert report.retake_recommendation == 'RETAKE'
    quality_repository.save_report(report)


def test_profile_change_and_retake_preserve_old_reports_and_do_not_reassign_campaign_evidence(tmp_path: Path) -> None:
    revision, measurement_repository, quality_repository = _repositories(tmp_path)
    old_record, old_dataset = _save_measurement(
        measurement_repository,
        revision,
        'old',
        raw=b'old',
    )

    old_profile = build_measurement_quality_profile(profile_version='profile-1', minimum_snr_db=20.0)
    old_report = build_measurement_quality_report(
        measurement=old_record,
        dataset=old_dataset,
        evidence=CadMeasurementQualityEvidence(snr_db=25.0),
        profile=old_profile,
        report_id='old-report',
        created_at_utc='2026-09-19T00:05:00+00:00',
    )
    quality_repository.save_report(old_report)

    stricter_profile = build_measurement_quality_profile(
        profile_version='profile-2',
        minimum_snr_db=30.0,
    )
    recheck = build_measurement_quality_report(
        measurement=old_record,
        dataset=old_dataset,
        evidence=old_report.evidence,
        profile=stricter_profile,
        report_id='old-report-profile-2',
        created_at_utc='2026-09-19T00:06:00+00:00',
    )
    quality_repository.save_report(recheck)

    new_record, new_dataset = _save_measurement(
        measurement_repository,
        revision,
        'retake',
        raw=b'retake',
    )
    retake_report = build_measurement_quality_report(
        measurement=new_record,
        dataset=new_dataset,
        evidence=CadMeasurementQualityEvidence(snr_db=35.0),
        profile=stricter_profile,
        report_id='retake-report',
        created_at_utc='2026-09-19T00:07:00+00:00',
    )
    quality_repository.save_report(retake_report)
    lineage = build_measurement_lineage(
        document_id=revision.document_id,
        measurement_id=new_record.measurement_id,
        supersedes_measurement_id=old_record.measurement_id,
        selected_measurement_id=new_record.measurement_id,
        reason='explicit retake after quality review',
        lineage_id='retake-lineage',
        created_at_utc='2026-09-19T00:08:00+00:00',
    )
    quality_repository.save_lineage(lineage)

    reports = quality_repository.list_reports(old_record.measurement_id)
    assert reports == (old_report, recheck)
    assert quality_repository.get_report(old_report.report_id) == old_report
    assert old_report.profile.profile_sha256 != recheck.profile.profile_sha256
    assert old_report.noise_snr.status == 'PASS'
    assert recheck.noise_snr.status == 'FAIL'
    assert quality_repository.list_reports(new_record.measurement_id) == (retake_report,)
    assert quality_repository.list_lineage(revision.document_id) == (lineage,)
    assert quality_repository.selected_measurement_for_lineage(old_record.measurement_id) == new_record.measurement_id

    # Retake lineage is independent of preregistered O50/O60 calibration/holdout plans:
    # no measurement-plan or campaign row is created or rewritten as a side effect.
    assert measurement_repository.list_measurement_plans('not-a-search') == ()
