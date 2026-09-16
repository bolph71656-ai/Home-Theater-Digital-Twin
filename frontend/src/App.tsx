import { type FormEvent, useEffect, useMemo, useState } from 'react'
import { api, fileToBase64 } from './api'
import { FrequencyPlot, RoomPlot, type ComparisonResult, type ContextPayload, type Speaker } from './plots'

type Health = {
  status: string
  version: string
  platform_target: string
  schema_version: number
}

type Project = { id: string; name: string; created_at: string }
type ContextRecord = { id: string; revision_number: number; created_at: string; payload: ContextPayload }
type Measurement = {
  id: string
  dataset_id: string
  context_id: string
  channel_role: string
  evidence_type: string
  points: number
  frequency_min_hz: number
  frequency_max_hz: number
  metadata: { phase_status: string; warnings: string[] }
}
type Preview = {
  filename: string
  sha256: string
  points: number
  frequency_min_hz: number
  frequency_max_hz: number
  phase_status: string
  warnings: string[]
}
type Comparison = {
  id: string
  result: ComparisonResult
  spec: { label?: string | null }
}
type RoomMode = {
  n_x: number
  n_y: number
  n_z: number
  frequency_hz: number
  mode_class: string
}
type ReflectionCandidate = {
  speaker_id: string
  speaker_role: string
  surface: string
  reflection_point_m: [number, number, number]
  direct_length_m: number
  reflected_length_m: number
  excess_length_m: number
  excess_delay_ms: number
  first_destructive_hz: number | null
}
type AcousticAnalysis = {
  classification: 'predicted_geometry_candidate'
  algorithm_version: string
  assumptions: string[]
  sound_speed_m_s: number
  max_mode_hz: number
  room_modes: RoomMode[]
  first_order_reflections: ReflectionCandidate[]
  skipped_speaker_ids: string[]
}
type SpeakerDraft = {
  speaker_id: string
  role: string
  model: string
  x: string
  y: string
  z: string
}

type ExcludedBand = { low_hz: number; high_hz: number }

const initialSpeakers: SpeakerDraft[] = [
  { speaker_id: 'FL', role: 'front_left', model: '', x: '', y: '', z: '' },
  { speaker_id: 'C', role: 'front_center', model: '', x: '', y: '', z: '' },
  { speaker_id: 'FR', role: 'front_right', model: '', x: '', y: '', z: '' },
  { speaker_id: 'HL', role: 'height_front_left', model: '', x: '', y: '', z: '' },
  { speaker_id: 'HR', role: 'height_front_right', model: '', x: '', y: '', z: '' },
]

function numeric(value: string, label: string): number {
  const result = Number(value)
  if (!Number.isFinite(result)) throw new Error(`${label}を入力してください`)
  return result
}

function speakerPayload(draft: SpeakerDraft): Speaker {
  const coordinates = [draft.x, draft.y, draft.z]
  const hasAny = coordinates.some((value) => value.trim() !== '')
  const hasAll = coordinates.every((value) => value.trim() !== '')
  if (hasAny && !hasAll) throw new Error(`${draft.role}: 座標はX/Y/Zをすべて入力してください`)
  return {
    speaker_id: draft.speaker_id,
    role: draft.role,
    model: draft.model || null,
    position: hasAll
      ? { x_m: numeric(draft.x, 'X'), y_m: numeric(draft.y, 'Y'), z_m: numeric(draft.z, 'Z') }
      : null,
  }
}

function parseExcludedBands(text: string): ExcludedBand[] {
  if (!text.trim()) return []
  return text.split(/[,;]+/).map((chunk) => {
    const match = chunk.trim().match(/^([0-9]+(?:\.[0-9]+)?)\s*-\s*([0-9]+(?:\.[0-9]+)?)$/)
    if (!match) throw new Error(`除外帯域「${chunk.trim()}」は 70-90 の形式で入力してください`)
    const low_hz = Number(match[1])
    const high_hz = Number(match[2])
    if (low_hz <= 0 || high_hz <= low_hz) throw new Error(`除外帯域「${chunk.trim()}」が不正です`)
    return { low_hz, high_hz }
  })
}

export default function App() {
  const [health, setHealth] = useState<Health | null>(null)
  const [projects, setProjects] = useState<Project[]>([])
  const [projectId, setProjectId] = useState('')
  const [contexts, setContexts] = useState<ContextRecord[]>([])
  const [measurements, setMeasurements] = useState<Measurement[]>([])
  const [comparisons, setComparisons] = useState<Comparison[]>([])
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')

  const [projectName, setProjectName] = useState('Home Theater')
  const [room, setRoom] = useState({ width: '', depth: '', height: '' })
  const [mlp, setMlp] = useState({ x: '', y: '', z: '' })
  const [speakers, setSpeakers] = useState<SpeakerDraft[]>(initialSpeakers)

  const [selectedContextId, setSelectedContextId] = useState('')
  const [measurementFile, setMeasurementFile] = useState<File | null>(null)
  const [measurementBase64, setMeasurementBase64] = useState('')
  const [preview, setPreview] = useState<Preview | null>(null)
  const [channelRole, setChannelRole] = useState('front_left')
  const [sourceSpeakerIds, setSourceSpeakerIds] = useState('FL')

  const [datasetA, setDatasetA] = useState('')
  const [datasetB, setDatasetB] = useState('')
  const [band, setBand] = useState({ low: '60', high: '200', refLow: '60', refHigh: '200' })
  const [excludedBandsText, setExcludedBandsText] = useState('')
  const [activeComparison, setActiveComparison] = useState<Comparison | null>(null)

  const [maxModeHz, setMaxModeHz] = useState('300')
  const [soundSpeed, setSoundSpeed] = useState('343')
  const [acoustics, setAcoustics] = useState<AcousticAnalysis | null>(null)

  const activeContext = useMemo(
    () => contexts.find((context) => context.id === selectedContextId) ?? contexts[0] ?? null,
    [contexts, selectedContextId],
  )

  async function reloadProjects() {
    const items = await api<Project[]>('/api/projects')
    setProjects(items)
    if (!projectId && items[0]) setProjectId(items[0].id)
  }

  async function reloadProjectData(id: string) {
    if (!id) return
    const [contextRows, measurementRows, comparisonRows] = await Promise.all([
      api<ContextRecord[]>(`/api/projects/${id}/contexts`),
      api<Measurement[]>(`/api/projects/${id}/measurements`),
      api<Comparison[]>(`/api/projects/${id}/comparisons`),
    ])
    setContexts(contextRows)
    setMeasurements(measurementRows)
    setComparisons(comparisonRows)
    if (contextRows[0]) setSelectedContextId((current) => current || contextRows[0].id)
    if (measurementRows[0]) setDatasetA((current) => current || measurementRows[0].dataset_id)
    if (measurementRows[1]) setDatasetB((current) => current || measurementRows[1].dataset_id)
  }

  useEffect(() => {
    void Promise.all([api<Health>('/api/health').then(setHealth), reloadProjects()]).catch((reason: unknown) => {
      setError(reason instanceof Error ? reason.message : '初期化に失敗しました')
    })
  }, [])

  useEffect(() => {
    setSelectedContextId('')
    setDatasetA('')
    setDatasetB('')
    setActiveComparison(null)
    setAcoustics(null)
    void reloadProjectData(projectId).catch((reason: unknown) => setError(reason instanceof Error ? reason.message : '読込失敗'))
  }, [projectId])

  useEffect(() => {
    setAcoustics(null)
  }, [selectedContextId])

  function notify(text: string) {
    setMessage(text)
    setError('')
  }

  async function createProject(event: FormEvent) {
    event.preventDefault()
    try {
      const project = await api<Project>('/api/projects', { method: 'POST', body: JSON.stringify({ name: projectName }) })
      await reloadProjects()
      setProjectId(project.id)
      notify('プロジェクトを作成しました')
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '作成失敗')
    }
  }

  function copyActiveContextToEditor() {
    if (!activeContext) return
    const payload = activeContext.payload
    setRoom({
      width: String(payload.room.width_m),
      depth: String(payload.room.depth_m),
      height: String(payload.room.height_m),
    })
    setMlp({
      x: String(payload.measurement_point.position.x_m),
      y: String(payload.measurement_point.position.y_m),
      z: String(payload.measurement_point.position.z_m),
    })
    setSpeakers(payload.speakers.map((speaker) => ({
      speaker_id: speaker.speaker_id,
      role: speaker.role,
      model: speaker.model ?? '',
      x: speaker.position ? String(speaker.position.x_m) : '',
      y: speaker.position ? String(speaker.position.y_m) : '',
      z: speaker.position ? String(speaker.position.z_m) : '',
    })))
    notify(`R${activeContext.revision_number} を編集フォームへ複製しました。保存するまで元版は変わりません`)
  }

  async function saveContext(event: FormEvent) {
    event.preventDefault()
    try {
      if (!projectId) throw new Error('先にプロジェクトを作成してください')
      const payload = {
        room: {
          width_m: numeric(room.width, '部屋幅'),
          depth_m: numeric(room.depth, '部屋奥行'),
          height_m: numeric(room.height, '部屋高さ'),
        },
        speakers: speakers.map(speakerPayload),
        measurement_point: {
          point_id: 'MLP',
          label: 'MLP',
          position: { x_m: numeric(mlp.x, 'MLP X'), y_m: numeric(mlp.y, 'MLP Y'), z_m: numeric(mlp.z, 'MLP Z') },
        },
        avr: { manufacturer: 'Yamaha', model: 'RX-A4A' },
        parent_context_id: activeContext?.id ?? null,
      }
      const saved = await api<ContextRecord>(`/api/projects/${projectId}/contexts`, { method: 'POST', body: JSON.stringify(payload) })
      await reloadProjectData(projectId)
      setSelectedContextId(saved.id)
      notify(`配置・条件 R${saved.revision_number} を保存しました`)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '保存失敗')
    }
  }

  async function chooseMeasurementFile(file: File | null) {
    setMeasurementFile(file)
    setPreview(null)
    setMeasurementBase64('')
    if (!file) return
    try {
      const raw_base64 = await fileToBase64(file)
      setMeasurementBase64(raw_base64)
      const result = await api<Preview>('/api/import/preview', { method: 'POST', body: JSON.stringify({ filename: file.name, raw_base64 }) })
      setPreview(result)
      notify('取込プレビューを検証しました')
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'プレビュー失敗')
    }
  }

  async function importMeasurement() {
    try {
      if (!projectId || !selectedContextId || !measurementFile || !measurementBase64) throw new Error('プロジェクト、条件版、測定ファイルを選択してください')
      await api(`/api/projects/${projectId}/measurements`, {
        method: 'POST',
        body: JSON.stringify({
          filename: measurementFile.name,
          raw_base64: measurementBase64,
          context_id: selectedContextId,
          channel_role: channelRole,
          evidence_type: 'measured',
          source_speaker_ids: sourceSpeakerIds.split(',').map((value) => value.trim()).filter(Boolean),
          radiation_scope: 'unknown',
        }),
      })
      await reloadProjectData(projectId)
      setMeasurementFile(null)
      setMeasurementBase64('')
      setPreview(null)
      notify('測定を原本付きで保存しました')
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '取込失敗')
    }
  }

  async function compare() {
    try {
      if (!projectId || !datasetA || !datasetB) throw new Error('A/Bの測定を選択してください')
      const comparison = await api<Comparison>(`/api/projects/${projectId}/comparisons`, {
        method: 'POST',
        body: JSON.stringify({
          dataset_a_id: datasetA,
          dataset_b_id: datasetB,
          low_hz: numeric(band.low, '帯域下限'),
          high_hz: numeric(band.high, '帯域上限'),
          reference_low_hz: numeric(band.refLow, '基準帯域下限'),
          reference_high_hz: numeric(band.refHigh, '基準帯域上限'),
          excluded_bands: parseExcludedBands(excludedBandsText),
          label: 'Speaker setting A/B',
        }),
      })
      setActiveComparison(comparison)
      await reloadProjectData(projectId)
      notify('比較条件と結果を保存しました')
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '比較失敗')
    }
  }

  async function runAcoustics() {
    try {
      if (!projectId || !activeContext) throw new Error('配置版を選択してください')
      const maxHz = numeric(maxModeHz, 'モード上限')
      const speed = numeric(soundSpeed, '音速')
      const result = await api<AcousticAnalysis>(`/api/projects/${projectId}/contexts/${activeContext.id}/acoustics?max_hz=${encodeURIComponent(maxHz)}&sound_speed_m_s=${encodeURIComponent(speed)}`)
      setAcoustics(result)
      notify('幾何モデル候補を計算しました。実測診断とは別表示です')
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '解析失敗')
    }
  }

  async function restore(file: File | null) {
    if (!file) return
    try {
      const archive_base64 = await fileToBase64(file)
      await api('/api/restore', { method: 'POST', body: JSON.stringify({ archive_base64 }) })
      await reloadProjects()
      if (projectId) await reloadProjectData(projectId)
      notify('バックアップを復元しました')
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '復元失敗')
    }
  }

  return (
    <main className="shell">
      <header className="hero">
        <div>
          <p className="eyebrow">v0.2 foundation · measured evidence first</p>
          <h1>Home Theater Digital Twin</h1>
          <p className="lead">測定の再現性と配置履歴を固定し、A/B比較を積み重ねてスピーカーセッティングを改善します。幾何モデルは候補生成に限定します。</p>
        </div>
        <div className="runtime">
          <strong>{health?.status ?? 'checking'}</strong>
          <span>{health?.platform_target}</span>
          <span>schema {health?.schema_version ?? '—'}</span>
        </div>
      </header>

      {(message || error) && <div className={error ? 'notice error' : 'notice'}>{error || message}</div>}

      <section className="panel">
        <div className="section-title"><h2>1. Project</h2><span>ローカル保存</span></div>
        <form className="row" onSubmit={createProject}>
          <input value={projectName} onChange={(event) => setProjectName(event.target.value)} aria-label="Project name" />
          <button type="submit">新規作成</button>
          <select value={projectId} onChange={(event) => setProjectId(event.target.value)} aria-label="Project">
            <option value="">プロジェクトを選択</option>
            {projects.map((project) => <option key={project.id} value={project.id}>{project.name}</option>)}
          </select>
          <a className="button-link" href="/api/backup">バックアップZIP</a>
          <label className="button-link">復元ZIP<input hidden type="file" accept=".zip" onChange={(event) => void restore(event.target.files?.[0] ?? null)} /></label>
        </form>
      </section>

      <section className="panel">
        <div className="section-title"><h2>2. Room / Layout / AVR snapshot</h2><span>{contexts.length ? `${contexts.length} revisions` : '未登録'}</span></div>
        <form onSubmit={saveContext}>
          <div className="grid3">
            <label>幅 X (m)<input value={room.width} onChange={(event) => setRoom({ ...room, width: event.target.value })} /></label>
            <label>奥行 Y (m)<input value={room.depth} onChange={(event) => setRoom({ ...room, depth: event.target.value })} /></label>
            <label>高さ Z (m)<input value={room.height} onChange={(event) => setRoom({ ...room, height: event.target.value })} /></label>
          </div>
          <h3>MLP</h3>
          <div className="grid3">
            <label>X<input value={mlp.x} onChange={(event) => setMlp({ ...mlp, x: event.target.value })} /></label>
            <label>Y<input value={mlp.y} onChange={(event) => setMlp({ ...mlp, y: event.target.value })} /></label>
            <label>Z<input value={mlp.z} onChange={(event) => setMlp({ ...mlp, z: event.target.value })} /></label>
          </div>
          <h3>Speakers — 現在の3.0.2を初期行として表示。増減可能</h3>
          <div className="speaker-table">
            {speakers.map((speaker, index) => (
              <div className="speaker-row" key={`${speaker.speaker_id}-${index}`}>
                <input value={speaker.speaker_id} onChange={(event) => setSpeakers(speakers.map((item, i) => i === index ? { ...item, speaker_id: event.target.value } : item))} aria-label="Speaker ID" />
                <input value={speaker.role} onChange={(event) => setSpeakers(speakers.map((item, i) => i === index ? { ...item, role: event.target.value } : item))} aria-label="Speaker role" />
                <input placeholder="model" value={speaker.model} onChange={(event) => setSpeakers(speakers.map((item, i) => i === index ? { ...item, model: event.target.value } : item))} />
                {(['x', 'y', 'z'] as const).map((axis) => <input key={axis} placeholder={axis.toUpperCase()} value={speaker[axis]} onChange={(event) => setSpeakers(speakers.map((item, i) => i === index ? { ...item, [axis]: event.target.value } : item))} />)}
                <button type="button" className="ghost" onClick={() => setSpeakers(speakers.filter((_, i) => i !== index))}>削除</button>
              </div>
            ))}
          </div>
          <div className="row">
            <button type="button" className="ghost" onClick={() => setSpeakers([...speakers, { speaker_id: `SP${speakers.length + 1}`, role: 'other', model: '', x: '', y: '', z: '' }])}>スピーカー追加</button>
            <button type="submit">新しい不変版として保存</button>
            <select value={selectedContextId} onChange={(event) => setSelectedContextId(event.target.value)}>
              {contexts.map((context) => <option key={context.id} value={context.id}>R{context.revision_number}</option>)}
            </select>
            <button type="button" className="ghost" disabled={!activeContext} onClick={copyActiveContextToEditor}>選択版を複製して編集</button>
          </div>
        </form>
        {activeContext && <RoomPlot context={activeContext.payload} />}
      </section>

      <section className="panel">
        <div className="section-title"><h2>3. REW text import</h2><span>原本SHA-256保持</span></div>
        <div className="grid2">
          <label>測定ファイル<input type="file" accept=".txt,.dat,.frd" onChange={(event) => void chooseMeasurementFile(event.target.files?.[0] ?? null)} /></label>
          <label>条件版<select value={selectedContextId} onChange={(event) => setSelectedContextId(event.target.value)}><option value="">選択</option>{contexts.map((context) => <option key={context.id} value={context.id}>R{context.revision_number}</option>)}</select></label>
          <label>入力role<input value={channelRole} onChange={(event) => setChannelRole(event.target.value)} /></label>
          <label>実際の音源ID（カンマ区切り）<input value={sourceSpeakerIds} onChange={(event) => setSourceSpeakerIds(event.target.value)} /></label>
        </div>
        {preview && <div className="preview"><strong>{preview.filename}</strong><span>{preview.points} points</span><span>{preview.frequency_min_hz}–{preview.frequency_max_hz} Hz</span><span>phase: {preview.phase_status}</span><span>SHA {preview.sha256.slice(0, 12)}…</span>{preview.warnings.map((warning) => <em key={warning}>{warning}</em>)}</div>}
        <button disabled={!preview} onClick={() => void importMeasurement()}>この測定を保存</button>
        <p className="hint">測定品質は、REWのレベル/クリップ警告と同条件再測定が未取得の間は unknown と扱います。</p>
        <div className="cards">
          {measurements.map((measurement) => <article key={measurement.id}><strong>{measurement.channel_role}</strong><span>{measurement.points} pts · {measurement.frequency_min_hz}–{measurement.frequency_max_hz} Hz</span><span>quality: unknown · evidence: {measurement.evidence_type}</span><code>{measurement.dataset_id.slice(0, 8)}</code></article>)}
        </div>
      </section>

      <section className="panel">
        <div className="section-title"><h2>4. A/B comparison</h2><span>96 PPO / log₂ interpolation / A−B</span></div>
        <div className="grid2">
          <label>A<select value={datasetA} onChange={(event) => setDatasetA(event.target.value)}><option value="">選択</option>{measurements.map((measurement) => <option key={measurement.dataset_id} value={measurement.dataset_id}>{measurement.channel_role} · {measurement.dataset_id.slice(0, 8)}</option>)}</select></label>
          <label>B<select value={datasetB} onChange={(event) => setDatasetB(event.target.value)}><option value="">選択</option>{measurements.map((measurement) => <option key={measurement.dataset_id} value={measurement.dataset_id}>{measurement.channel_role} · {measurement.dataset_id.slice(0, 8)}</option>)}</select></label>
        </div>
        <div className="grid4">
          <label>評価Low Hz<input value={band.low} onChange={(event) => setBand({ ...band, low: event.target.value })} /></label>
          <label>評価High Hz<input value={band.high} onChange={(event) => setBand({ ...band, high: event.target.value })} /></label>
          <label>基準Low Hz<input value={band.refLow} onChange={(event) => setBand({ ...band, refLow: event.target.value })} /></label>
          <label>基準High Hz<input value={band.refHigh} onChange={(event) => setBand({ ...band, refHigh: event.target.value })} /></label>
        </div>
        <label>除外帯域（例: 70-90, 120-130）<input value={excludedBandsText} onChange={(event) => setExcludedBandsText(event.target.value)} placeholder="任意" /></label>
        <div className="row action-row"><button onClick={() => void compare()}>比較して保存</button></div>
        {activeComparison && <>
          <div className="metrics">
            <div><span>Mean A−B</span><strong>{activeComparison.result.mean_difference_db?.toFixed(2) ?? '—'} dB</strong></div>
            <div><span>RMS diff</span><strong>{activeComparison.result.rms_difference_db?.toFixed(2) ?? '—'} dB</strong></div>
            <div><span>Level offset</span><strong>{activeComparison.result.level_offset_db?.toFixed(2) ?? '—'} dB</strong></div>
            <div><span>Shape RMS</span><strong>{activeComparison.result.shape_rms_db?.toFixed(2) ?? '—'} dB</strong></div>
          </div>
          <FrequencyPlot result={activeComparison.result} />
        </>}
        {!activeComparison && comparisons[0] && <button className="ghost" onClick={() => setActiveComparison(comparisons[0])}>最新の保存済み比較を表示</button>}
      </section>

      <section className="panel">
        <div className="section-title"><h2>5. Geometry candidates</h2><span>予測候補 · 実測診断ではない</span></div>
        <p className="hint">矩形室の固有周波数と、各スピーカー→MLPの一次鏡像反射を計算します。壁の吸音率、反射位相、スピーカーの指向性、開口や家具はまだモデル化しません。</p>
        <div className="grid3">
          <label>Room mode上限 (Hz)<input value={maxModeHz} onChange={(event) => setMaxModeHz(event.target.value)} /></label>
          <label>音速 (m/s)<input value={soundSpeed} onChange={(event) => setSoundSpeed(event.target.value)} /></label>
          <div className="field-action"><button disabled={!activeContext} onClick={() => void runAcoustics()}>選択版を解析</button></div>
        </div>
        {acoustics && <>
          <div className="analysis-banner"><strong>{acoustics.classification}</strong><span>{acoustics.algorithm_version}</span><span>c={acoustics.sound_speed_m_s} m/s</span></div>
          {acoustics.skipped_speaker_ids.length > 0 && <p className="hint">座標未入力のため反射計算を省略: {acoustics.skipped_speaker_ids.join(', ')}</p>}
          <h3>Room modes（先頭24件）</h3>
          <div className="analysis-grid">
            {acoustics.room_modes.slice(0, 24).map((mode) => <div key={`${mode.n_x}-${mode.n_y}-${mode.n_z}`}><strong>{mode.frequency_hz.toFixed(1)} Hz</strong><span>({mode.n_x},{mode.n_y},{mode.n_z}) · {mode.mode_class}</span></div>)}
          </div>
          <h3>一次反射候補</h3>
          <div className="analysis-grid wide">
            {acoustics.first_order_reflections.map((candidate) => <div key={`${candidate.speaker_id}-${candidate.surface}`}><strong>{candidate.speaker_id} · {candidate.surface}</strong><span>ΔL {candidate.excess_length_m.toFixed(3)} m · +{candidate.excess_delay_ms.toFixed(2)} ms</span><span>180°幾何候補 {candidate.first_destructive_hz ? `${candidate.first_destructive_hz.toFixed(1)} Hz` : '—'}</span></div>)}
          </div>
        </>}
      </section>
    </main>
  )
}
