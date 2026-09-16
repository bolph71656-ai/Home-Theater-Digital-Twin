import { useEffect, useRef } from 'react'
import Plotly, { type Data, type Layout } from 'plotly.js-dist-min'

export type Speaker = {
  speaker_id: string
  role: string
  model?: string | null
  position?: { x_m: number; y_m: number; z_m: number } | null
}

export type ContextPayload = {
  room: { width_m: number; depth_m: number; height_m: number }
  speakers: Speaker[]
  measurement_point: {
    label: string
    position: { x_m: number; y_m: number; z_m: number }
  }
}

export type ComparisonResult = {
  grid_hz: number[]
  a_db: number[]
  b_db: number[]
  difference_db: number[]
  mean_difference_db: number | null
  rms_difference_db: number | null
  level_offset_db: number | null
  shape_rms_db: number | null
  valid_points: number
  total_grid_points: number
  actual_band_hz: [number, number]
}

function usePlot(data: Data[], layout: Partial<Layout>) {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!ref.current) return
    void Plotly.react(ref.current, data, layout, {
      responsive: true,
      displaylogo: false,
      scrollZoom: true,
    })
    return () => {
      if (ref.current) Plotly.purge(ref.current)
    }
  }, [data, layout])
  return ref
}

export function FrequencyPlot({ result }: { result: ComparisonResult }) {
  const data: Data[] = [
    { type: 'scatter', mode: 'lines', name: 'A', x: result.grid_hz, y: result.a_db },
    { type: 'scatter', mode: 'lines', name: 'B', x: result.grid_hz, y: result.b_db },
  ]
  const layout: Partial<Layout> = {
    autosize: true,
    height: 420,
    margin: { l: 60, r: 20, t: 30, b: 55 },
    xaxis: { type: 'log', title: { text: 'Frequency (Hz)' } },
    yaxis: { title: { text: 'Level (dB)' } },
    legend: { orientation: 'h' },
  }
  const ref = usePlot(data, layout)
  return <div ref={ref} className="plot" aria-label="A/B frequency response plot" />
}

export function RoomPlot({ context }: { context: ContextPayload }) {
  const positioned = context.speakers.filter((speaker) => speaker.position)
  const speakerTrace: Data = {
    type: 'scatter3d',
    mode: 'markers+text',
    name: 'Speakers',
    x: positioned.map((speaker) => speaker.position!.x_m),
    y: positioned.map((speaker) => speaker.position!.z_m),
    z: positioned.map((speaker) => speaker.position!.y_m),
    text: positioned.map((speaker) => speaker.role),
    textposition: 'top center',
    marker: { size: 6 },
  }
  const mlp = context.measurement_point.position
  const listenerTrace: Data = {
    type: 'scatter3d',
    mode: 'markers+text',
    name: context.measurement_point.label,
    x: [mlp.x_m],
    y: [mlp.z_m],
    z: [mlp.y_m],
    text: [context.measurement_point.label],
    textposition: 'top center',
    marker: { size: 7 },
  }
  const layout: Partial<Layout> = {
    autosize: true,
    height: 430,
    margin: { l: 0, r: 0, t: 20, b: 0 },
    scene: {
      xaxis: { title: { text: 'X right (m)' }, range: [0, context.room.width_m] },
      yaxis: { title: { text: 'Z up (m)' }, range: [0, context.room.height_m] },
      zaxis: { title: { text: 'Y rear (m)' }, range: [0, context.room.depth_m] },
      aspectmode: 'data',
    },
    legend: { orientation: 'h' },
  }
  const ref = usePlot([speakerTrace, listenerTrace], layout)
  return <div ref={ref} className="plot" aria-label="Room spatial plot" />
}
