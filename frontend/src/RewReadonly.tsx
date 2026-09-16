import { useEffect, useMemo, useState } from 'react'
import { api } from './api'

type RewStatus = {
  connected: boolean
  read_only: boolean
  base_url: string
  measurement_count: number | null
  error: string | null
}

type RewAudioPreflight = {
  read_only: boolean
  audio_enabled: boolean | null
  audio_ready: boolean | null
  driver: string
  sample_rate_hz: number | null
  sample_rate_unit: string | null
  java: null | {
    input_device: string | null
    input_devices: string[]
    hardware_input_channels: number
    input: string | null
    inputs: string[]
    input_channel: number | null
    input_channels: number
    input_endpoint_ready: boolean
    input_cal_selection: string | null
    input_cal_file: string | null
    input_cal_file_present: boolean
    output_device: string | null
    output_devices: string[]
    hardware_output_channels: number
    output_channels: string[]
    output_channel_mapping: Array<{ index?: number; hardwareChannel?: number; channelLabel?: string }>
    stereo_only: boolean | null
    exclusive_output_candidates: string[]
    current_output_is_exclusive: boolean
    multichannel_ready: boolean
  }
  warnings: string[]
}

type RewMeasurement = Record<string, unknown> & {
  uuid?: string
  title?: string
  name?: string
}

type RewFrequencyResponse = {
  measurement_id: string
  unit: string | null
  smoothing: string | null
  start_frequency_hz: number
  points_per_octave: number | null
  frequency_step_hz: number | null
  frequency_hz: number[]
  magnitude: number[]
  phase_deg: number[] | null
  requested_unit: string
  requested_ppo: number | null
  requested_smoothing: string | null
}

function measurementLabel(measurement: RewMeasurement): string {
  const title = typeof measurement.title === 'string' && measurement.title.trim()
    ? measurement.title.trim()
    : typeof measurement.name === 'string' && measurement.name.trim()
      ? measurement.name.trim()
      : null
  const uuid = typeof measurement.uuid === 'string' ? measurement.uuid : ''
  if (title && uuid) return `${title} · ${uuid.slice(0, 8)}`
  return title || uuid || 'unnamed measurement'
}

function validMeasurementId(measurement: RewMeasurement): string | null {
  return typeof measurement.uuid === 'string' && measurement.uuid.trim() ? measurement.uuid : null
}

function finiteRange(values: number[]): { min: number; max: number } | null {
  const finite = values.filter(Number.isFinite)
  if (!finite.length) return null
  return { min: Math.min(...finite), max: Math.max(...finite) }
}

function FrequencyPreview({ response }: { response: RewFrequencyResponse }) {
  const geometry = useMemo(() => {
    const points = response.frequency_hz
      .map((frequency, index) => ({ frequency, level: response.magnitude[index] }))
      .filter((point) => Number.isFinite(point.frequency) && point.frequency > 0 && Number.isFinite(point.level))
    if (points.length < 2) return null

    const frequencyRange = finiteRange(points.map((point) => point.frequency))
    const levelRange = finiteRange(points.map((point) => point.level))
    if (!frequencyRange || !levelRange || frequencyRange.min === frequencyRange.max) return null

    const width = 960
    const height = 300
    const left = 56
    const right = 18
    const top = 18
    const bottom = 38
    const plotWidth = width - left - right
    const plotHeight = height - top - bottom
    const logMin = Math.log2(frequencyRange.min)
    const logMax = Math.log2(frequencyRange.max)
    const levelPadding = Math.max(1, (levelRange.max - levelRange.min) * 0.08)
    const levelMin = levelRange.min - levelPadding
    const levelMax = levelRange.max + levelPadding

    const x = (frequency: number) => left + ((Math.log2(frequency) - logMin) / (logMax - logMin)) * plotWidth
    const y = (level: number) => top + ((levelMax - level) / (levelMax - levelMin)) * plotHeight
    const polyline = points.map((point) => `${x(point.frequency).toFixed(2)},${y(point.level).toFixed(2)}`).join(' ')
    const frequencyTicks = [20, 50, 100, 200, 500, 1000, 2000, 5000, 10000, 20000]
      .filter((frequency) => frequency >= frequencyRange.min && frequency <= frequencyRange.max)
    const levelTicks = Array.from({ length: 5 }, (_, index) => levelMin + (index * (levelMax - levelMin)) / 4)

    return { width, height, left, top, plotWidth, plotHeight, x, y, polyline, frequencyTicks, levelTicks, levelMin, levelMax }
  }, [response])

  if (!geometry) return <p className="hint">FRプレビューに必要な有効点が不足しています。</p>

  return (
    <svg className="rew-fr-preview" viewBox={`0 0 ${geometry.width} ${geometry.height}`} role="img" aria-label="REW frequency response preview">
      <rect x={geometry.left} y={geometry.top} width={geometry.plotWidth} height={geometry.plotHeight} fill="white" stroke="currentColor" opacity="0.18" />
      {geometry.frequencyTicks.map((frequency) => (
        <g key={frequency}>
          <line x1={geometry.x(frequency)} x2={geometry.x(frequency)} y1={geometry.top} y2={geometry.top + geometry.plotHeight} stroke="currentColor" opacity="0.10" />
          <text x={geometry.x(frequency)} y={geometry.height - 12} textAnchor="middle" fontSize="11" fill="currentColor">{frequency >= 1000 ? `${frequency / 1000}k` : frequency}</text>
        </g>
      ))}
      {geometry.levelTicks.map((level) => (
        <g key={level}>
          <line x1={geometry.left} x2={geometry.left + geometry.plotWidth} y1={geometry.y(level)} y2={geometry.y(level)} stroke="currentColor" opacity="0.10" />
          <text x={geometry.left - 8} y={geometry.y(level) + 4} textAnchor="end" fontSize="11" fill="currentColor">{level.toFixed(1)}</text>
        </g>
      ))}
      <polyline points={geometry.polyline} fill="none" stroke="currentColor" strokeWidth="2" vectorEffect="non-scaling-stroke" />
      <text x={geometry.left + geometry.plotWidth / 2} y={geometry.height - 1} textAnchor="middle" fontSize="11" fill="currentColor">Frequency (Hz, log)</text>
      <text x="12" y={geometry.top + geometry.plotHeight / 2} textAnchor="middle" fontSize="11" fill="currentColor" transform={`rotate(-90 12 ${geometry.top + geometry.plotHeight / 2})`}>Magnitude ({response.unit ?? response.requested_unit})</text>
    </svg>
  )
}

export function RewReadonlyPanel() {
  const [status, setStatus] = useState<RewStatus | null>(null)
  const [measurements, setMeasurements] = useState<RewMeasurement[]>([])
  const [preflight, setPreflight] = useState<RewAudioPreflight | null>(null)
  const [selectedId, setSelectedId] = useState('')
  const [ppo, setPpo] = useState('96')
  const [unit, setUnit] = useState('SPL')
  const [smoothing, setSmoothing] = useState('')
  const [response, setResponse] = useState<RewFrequencyResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  async function refreshStatus() {
    setLoading(true)
    setError('')
    setResponse(null)
    try {
      const nextStatus = await api<RewStatus>('/api/rew/status')
      setStatus(nextStatus)
      if (!nextStatus.connected) {
        setMeasurements([])
        setPreflight(null)
        setSelectedId('')
        return
      }
      const [rows, audio] = await Promise.all([
        api<RewMeasurement[]>('/api/rew/measurements'),
        api<RewAudioPreflight>('/api/rew/audio-preflight'),
      ])
      setMeasurements(rows)
      setPreflight(audio)
      const firstId = rows.map(validMeasurementId).find((id): id is string => id !== null) ?? ''
      setSelectedId((current) => rows.some((item) => validMeasurementId(item) === current) ? current : firstId)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'REW状態の取得に失敗しました')
    } finally {
      setLoading(false)
    }
  }

  async function preview() {
    if (!selectedId) return
    const parsedPpo = Number(ppo)
    if (!Number.isInteger(parsedPpo) || parsedPpo < 1 || parsedPpo > 384) {
      setError('PPOは1〜384の整数で指定してください')
      return
    }
    setLoading(true)
    setError('')
    try {
      const query = new URLSearchParams({ ppo: String(parsedPpo), unit: unit.trim() || 'SPL' })
      if (smoothing.trim()) query.set('smoothing', smoothing.trim())
      const next = await api<RewFrequencyResponse>(`/api/rew/measurements/${encodeURIComponent(selectedId)}/frequency-response?${query.toString()}`)
      setResponse(next)
    } catch (reason) {
      setResponse(null)
      setError(reason instanceof Error ? reason.message : 'FRの取得に失敗しました')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void refreshStatus()
  }, [])

  const selectableMeasurements = measurements.filter((measurement) => validMeasurementId(measurement) !== null)

  const umik1Visible = preflight?.java?.input_devices.some((name) => /UMIK[- ]?1/i.test(name)) ?? false
  const currentInputIsUmik1 = /UMIK[- ]?1/i.test(preflight?.java?.input_device ?? '')
  const umik1RateReady = preflight?.sample_rate_hz === 48000
  const surroundCalHint = preflight?.java?.input_cal_file?.toLowerCase().includes('_90deg') ?? false

  return (
    <main className="shell supplemental-shell">
      <section className="panel">
        <div className="section-title">
          <h2>REW read-only browser</h2>
          <span>localhost GET only · preview only</span>
        </div>
        <p className="hint">
          REW 5.40系の読取専用APIを確認する補助画面です。測定開始、Generator、REW設定変更、HTDT Datasetへの保存は行いません。
        </p>
        <div className="row action-row">
          <button type="button" className="ghost" disabled={loading} onClick={() => void refreshStatus()}>{loading ? '確認中…' : 'REW接続を再確認'}</button>
          {status && <span className="hint">{status.base_url} · read-only: {status.read_only ? 'yes' : 'no'}</span>}
        </div>

        {error && <div className="notice error">{error}</div>}

        {status && !status.connected && (
          <div className="analysis-banner">
            <strong>offline</strong>
            <span>REW未起動でもHTDTの保存済みデータは通常利用できます。</span>
            {status.error && <span>{status.error}</span>}
          </div>
        )}

        {status?.connected && (
          <>
            <div className="analysis-banner">
              <strong>connected · read-only</strong>
              <span>{status.measurement_count ?? measurements.length} measurement(s)</span>
              <span>REWへのHTTP GETのみ</span>
            </div>
            {preflight && <div className="preview rew-preflight">
              <strong>Measurement audio preflight</strong>
              <span>driver: {preflight.driver} · audio ready: {preflight.audio_ready === null ? 'unknown' : preflight.audio_ready ? 'yes' : 'no'}</span>
              <span>sample rate: {preflight.sample_rate_hz ?? 'unknown'} {preflight.sample_rate_unit ?? ''}</span>
              <span>target mic: miniDSP UMIK-1 · visible: {umik1Visible ? 'yes' : 'no'} · selected: {currentInputIsUmik1 ? 'yes' : 'no'} · 48 kHz: {umik1RateReady ? 'yes' : 'no'}</span>
              {preflight.java ? <>
                <span>input: {preflight.java.input_device ?? 'unknown'} · {preflight.java.input ?? 'unknown'} · ch {preflight.java.input_channel ?? 'unknown'}/{preflight.java.input_channels}</span>
                <span>input endpoint ready: {preflight.java.input_endpoint_ready ? 'yes' : 'no'} · mic cal file: {preflight.java.input_cal_file_present ? preflight.java.input_cal_file : 'not selected'}</span>
                <span>HTDT surround baseline: ceiling orientation + UMIK-1 90° cal · filename hint: {surroundCalHint ? '90deg' : 'not confirmed'}</span>
                <span>output: {preflight.java.output_device ?? 'unknown'}</span>
                <span>hardware channels: {preflight.java.hardware_output_channels} · stereo-only: {preflight.java.stereo_only === null ? 'unknown' : preflight.java.stereo_only ? 'yes' : 'no'}</span>
                <span>WASAPI Exclusive: {preflight.java.current_output_is_exclusive ? 'selected' : 'not selected'} · multichannel ready: {preflight.java.multichannel_ready ? 'yes' : 'no'}</span>
                <span>EXCL candidates: {preflight.java.exclusive_output_candidates.length ? preflight.java.exclusive_output_candidates.join(' / ') : 'none'}</span>
                <span>mapping: {preflight.java.output_channel_mapping.length ? preflight.java.output_channel_mapping.map((item) => `${item.channelLabel ?? '?'}→HW${item.hardwareChannel ?? '?'}`).join(', ') : 'none'}</span>
              </> : <span>Java output preflight is not applicable for the selected driver.</span>}
              {preflight.warnings.map((warning) => <em key={warning}>{warning}</em>)}
            </div>}
            <div className="grid4 rew-controls">
              <label>Measurement
                <select value={selectedId} onChange={(event) => { setSelectedId(event.target.value); setResponse(null) }}>
                  <option value="">選択</option>
                  {selectableMeasurements.map((measurement) => {
                    const id = validMeasurementId(measurement)!
                    return <option key={id} value={id}>{measurementLabel(measurement)}</option>
                  })}
                </select>
              </label>
              <label>Requested PPO<input inputMode="numeric" value={ppo} onChange={(event) => setPpo(event.target.value)} /></label>
              <label>Unit<input value={unit} onChange={(event) => setUnit(event.target.value)} /></label>
              <label>Smoothing<input value={smoothing} onChange={(event) => setSmoothing(event.target.value)} placeholder="空欄=指定なし" /></label>
            </div>
            <div className="row action-row">
              <button type="button" disabled={!selectedId || loading} onClick={() => void preview()}>{loading ? '取得中…' : '96 PPO FRをプレビュー'}</button>
              {measurements.length > selectableMeasurements.length && <span className="hint">UUIDを持たない項目はFR選択から除外しています。</span>}
            </div>
          </>
        )}

        {response && (
          <>
            <div className="metrics rew-metrics">
              <div><span>Points</span><strong>{response.frequency_hz.length}</strong></div>
              <div><span>Range</span><strong>{response.frequency_hz[0]?.toFixed(1) ?? '—'}–{response.frequency_hz.at(-1)?.toFixed(1) ?? '—'} Hz</strong></div>
              <div><span>Requested</span><strong>{response.requested_ppo ?? '—'} PPO · {response.requested_unit}</strong></div>
              <div><span>Returned</span><strong>{response.points_per_octave ?? 'linear'} PPO · {response.unit ?? 'unknown'}</strong></div>
            </div>
            <div className="preview">
              <strong>Provenance</strong>
              <span>requested smoothing: {response.requested_smoothing ?? 'none'}</span>
              <span>returned smoothing: {response.smoothing ?? 'unknown/none'}</span>
              <span>phase: {response.phase_deg ? `${response.phase_deg.length} points` : 'not returned'}</span>
            </div>
            <FrequencyPreview response={response} />
            <p className="hint">この曲線はREWからその場でGETしたプレビューです。HTDTのMeasurement/Datasetには保存していません。</p>
          </>
        )}
      </section>
    </main>
  )
}
