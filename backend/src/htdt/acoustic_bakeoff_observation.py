from __future__ import annotations

from math import atan2, degrees, isfinite, sqrt
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .acoustic_bakeoff import (
    BakeoffFixtureEvidence,
    BakeoffObservableEvidence,
    observable_tolerance_violations,
)
from .acoustic_benchmark import (
    AcousticBenchmarkFixture,
    BenchmarkObservableKind,
)


class RawObservationSample(BaseModel):
    """Backend-produced value before any R100A pass/fail judgment."""

    model_config = ConfigDict(frozen=True)

    sample_key: str = Field(min_length=1)
    frequency_hz: float | None = Field(default=None, gt=0.0)
    scalar_value: float | None = None
    real_value: float | None = None
    imag_value: float | None = None
    vector_value: tuple[float, float, float] | None = None

    @model_validator(mode='after')
    def exactly_one_finite_representation(self) -> 'RawObservationSample':
        scalar = self.scalar_value is not None
        complex_value = self.real_value is not None or self.imag_value is not None
        vector = self.vector_value is not None
        if sum((scalar, complex_value, vector)) != 1:
            raise ValueError('raw observation sample must use exactly one value representation')
        if complex_value and (self.real_value is None or self.imag_value is None):
            raise ValueError('raw complex sample requires both real_value and imag_value')

        values: list[float] = []
        if self.frequency_hz is not None:
            values.append(self.frequency_hz)
        if self.scalar_value is not None:
            values.append(self.scalar_value)
        if self.real_value is not None:
            values.extend((self.real_value, self.imag_value or 0.0))
        if self.vector_value is not None:
            values.extend(self.vector_value)
        if any(not isfinite(float(value)) for value in values):
            raise ValueError('raw observation values must be finite')
        return self


class RawObservableObservation(BaseModel):
    model_config = ConfigDict(frozen=True)

    observable_id: str = Field(min_length=1)
    kind: BenchmarkObservableKind
    unit: str = Field(min_length=1)
    samples: tuple[RawObservationSample, ...] = Field(min_length=1)
    diagnostics: tuple[str, ...] = ()

    @model_validator(mode='after')
    def unique_sample_keys(self) -> 'RawObservableObservation':
        keys = [item.sample_key for item in self.samples]
        if len(keys) != len(set(keys)):
            raise ValueError('raw observation sample keys must be unique')
        return self


class RawFixtureObservation(BaseModel):
    model_config = ConfigDict(frozen=True)

    fixture_id: str = Field(min_length=1)
    evidence_ref: str = Field(min_length=1)
    adapter_id: str = Field(min_length=1)
    adapter_version: str = Field(min_length=1)
    backend_version: str = Field(min_length=1)
    precision: Literal['float32', 'float64', 'mixed']
    compile_s: float = Field(ge=0.0)
    solve_s: float = Field(ge=0.0)
    postprocess_s: float = Field(ge=0.0)
    peak_ram_mb: float = Field(ge=0.0)
    output_mb: float = Field(ge=0.0)
    observations: tuple[RawObservableObservation, ...] = Field(min_length=1)
    diagnostics: tuple[str, ...] = ()

    @model_validator(mode='after')
    def finite_resources_and_unique_observables(self) -> 'RawFixtureObservation':
        resources = (
            self.compile_s,
            self.solve_s,
            self.postprocess_s,
            self.peak_ram_mb,
            self.output_mb,
        )
        if any(not isfinite(float(value)) for value in resources):
            raise ValueError('raw fixture resource metrics must be finite')
        ids = [item.observable_id for item in self.observations]
        if len(ids) != len(set(ids)):
            raise ValueError('raw fixture observable ids must be unique')
        return self


def _relative_error(absolute_error: float, expected_magnitude: float) -> float | None:
    if expected_magnitude == 0.0:
        return None
    return absolute_error / expected_magnitude


def _wrapped_phase_error_deg(
    raw_real: float,
    raw_imag: float,
    expected_real: float,
    expected_imag: float,
) -> float | None:
    raw_magnitude = sqrt(raw_real * raw_real + raw_imag * raw_imag)
    expected_magnitude = sqrt(expected_real * expected_real + expected_imag * expected_imag)
    if raw_magnitude == 0.0 or expected_magnitude == 0.0:
        return None
    raw_phase = degrees(atan2(raw_imag, raw_real))
    expected_phase = degrees(atan2(expected_imag, expected_real))
    return abs((raw_phase - expected_phase + 180.0) % 360.0 - 180.0)


def _max_or_none(values: list[float]) -> float | None:
    return max(values) if values else None


def _evaluate_sample_pair(expected, raw: RawObservationSample) -> tuple[float | None, float | None, float | None]:
    if expected.frequency_hz is not None:
        if raw.frequency_hz is None:
            raise ValueError(f'raw sample {raw.sample_key} is missing frequency_hz')
        frequency_tolerance = max(1e-9, abs(expected.frequency_hz) * 1e-12)
        if abs(raw.frequency_hz - expected.frequency_hz) > frequency_tolerance:
            raise ValueError(
                f'raw sample {raw.sample_key} frequency does not match authority: '
                f'{raw.frequency_hz} != {expected.frequency_hz}'
            )
    elif raw.frequency_hz is not None:
        raise ValueError(f'raw sample {raw.sample_key} adds an undeclared frequency')

    if expected.scalar_value is not None:
        if raw.scalar_value is None:
            raise ValueError(f'raw sample {raw.sample_key} does not provide scalar_value')
        absolute = abs(raw.scalar_value - expected.scalar_value)
        return absolute, _relative_error(absolute, abs(expected.scalar_value)), None

    if expected.real_value is not None and expected.imag_value is not None:
        if raw.real_value is None or raw.imag_value is None:
            raise ValueError(f'raw sample {raw.sample_key} does not provide a complex value')
        diff_real = raw.real_value - expected.real_value
        diff_imag = raw.imag_value - expected.imag_value
        absolute = sqrt(diff_real * diff_real + diff_imag * diff_imag)
        expected_magnitude = sqrt(
            expected.real_value * expected.real_value + expected.imag_value * expected.imag_value
        )
        return (
            absolute,
            _relative_error(absolute, expected_magnitude),
            _wrapped_phase_error_deg(
                raw.real_value,
                raw.imag_value,
                expected.real_value,
                expected.imag_value,
            ),
        )

    if expected.vector_value is not None:
        if raw.vector_value is None:
            raise ValueError(f'raw sample {raw.sample_key} does not provide vector_value')
        delta = tuple(
            raw_value - expected_value
            for raw_value, expected_value in zip(raw.vector_value, expected.vector_value)
        )
        absolute = sqrt(sum(value * value for value in delta))
        expected_magnitude = sqrt(sum(value * value for value in expected.vector_value))
        return absolute, _relative_error(absolute, expected_magnitude), None

    raise ValueError(f'expected sample {expected.sample_key} has no supported value representation')


def evaluate_sampled_observable(expected, raw: RawObservableObservation) -> BakeoffObservableEvidence:
    if not expected.samples:
        raise ValueError(
            f'observable {expected.observable_id} has no expected samples; '
            'a specialized R100B evaluator is required'
        )
    if raw.observable_id != expected.observable_id:
        raise ValueError(
            f'raw observable id {raw.observable_id} does not match {expected.observable_id}'
        )
    if raw.kind != expected.kind:
        raise ValueError(
            f'raw observable {raw.observable_id} kind {raw.kind} does not match {expected.kind}'
        )
    if raw.unit != expected.unit:
        raise ValueError(
            f'raw observable {raw.observable_id} unit {raw.unit} does not match {expected.unit}'
        )

    expected_by_key = {item.sample_key: item for item in expected.samples}
    raw_by_key = {item.sample_key: item for item in raw.samples}
    if set(raw_by_key) != set(expected_by_key):
        raise ValueError(
            f'raw observable {raw.observable_id} sample keys do not match authority: '
            f'expected={sorted(expected_by_key)} actual={sorted(raw_by_key)}'
        )

    absolute_errors: list[float] = []
    relative_errors: list[float] = []
    phase_errors: list[float] = []
    for sample_key, expected_sample in expected_by_key.items():
        absolute, relative, phase = _evaluate_sample_pair(expected_sample, raw_by_key[sample_key])
        if absolute is not None:
            absolute_errors.append(absolute)
        if relative is not None:
            relative_errors.append(relative)
        if phase is not None:
            phase_errors.append(phase)

    provisional = BakeoffObservableEvidence(
        observable_id=expected.observable_id,
        status='pass',
        summary='raw backend observations compared against R100A expected samples',
        absolute_error=_max_or_none(absolute_errors),
        relative_error=_max_or_none(relative_errors),
        phase_error_deg=_max_or_none(phase_errors),
    )
    violations = observable_tolerance_violations(expected, provisional)
    if not violations:
        return provisional

    return BakeoffObservableEvidence(
        observable_id=expected.observable_id,
        status='fail',
        summary='; '.join(violations),
        absolute_error=provisional.absolute_error,
        relative_error=provisional.relative_error,
        phase_error_deg=provisional.phase_error_deg,
    )


def evaluate_sampled_fixture(
    fixture: AcousticBenchmarkFixture,
    raw: RawFixtureObservation,
) -> BakeoffFixtureEvidence:
    """Convert raw third-party observations into R100B evidence using R100A authority."""

    if raw.fixture_id != fixture.fixture_id:
        raise ValueError(
            f'raw fixture id {raw.fixture_id} does not match authority fixture {fixture.fixture_id}'
        )

    expected_by_id = {item.observable_id: item for item in fixture.observables}
    raw_by_id = {item.observable_id: item for item in raw.observations}
    if set(raw_by_id) != set(expected_by_id):
        raise ValueError(
            f'raw fixture {raw.fixture_id} observable ids do not match authority: '
            f'expected={sorted(expected_by_id)} actual={sorted(raw_by_id)}'
        )

    evidence = tuple(
        evaluate_sampled_observable(expected, raw_by_id[observable_id])
        for observable_id, expected in expected_by_id.items()
    )
    status: Literal['pass', 'fail'] = (
        'pass' if all(item.status == 'pass' for item in evidence) else 'fail'
    )
    return BakeoffFixtureEvidence(
        fixture_id=fixture.fixture_id,
        status=status,
        evidence_ref=raw.evidence_ref,
        adapter_id=raw.adapter_id,
        adapter_version=raw.adapter_version,
        backend_version=raw.backend_version,
        precision=raw.precision,
        compile_s=raw.compile_s,
        solve_s=raw.solve_s,
        postprocess_s=raw.postprocess_s,
        peak_ram_mb=raw.peak_ram_mb,
        output_mb=raw.output_mb,
        observables=evidence,
        diagnostics=raw.diagnostics,
    )
