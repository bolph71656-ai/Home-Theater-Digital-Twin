import { useEffect, useState } from 'react'

type Health = {
  status: string
  version: string
  platform_target: string
  rew_required: boolean
  measurement_hardware_required: boolean
}

export default function App() {
  const [health, setHealth] = useState<Health | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const controller = new AbortController()

    fetch('/api/health', { signal: controller.signal })
      .then(async (response) => {
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`)
        }
        return response.json() as Promise<Health>
      })
      .then(setHealth)
      .catch((reason: unknown) => {
        if (reason instanceof DOMException && reason.name === 'AbortError') {
          return
        }
        setError(reason instanceof Error ? reason.message : 'Unknown error')
      })

    return () => controller.abort()
  }, [])

  return (
    <main className="shell">
      <header>
        <p className="eyebrow">M01 · bootstrap</p>
        <h1>Home Theater Digital Twin</h1>
        <p className="lead">
          実測・配置・AVR設定の履歴を結び、再現可能なA/B比較からスピーカーセッティングを改善するローカルツール。
        </p>
      </header>

      <section className="panel">
        <h2>Runtime</h2>
        {health && (
          <dl>
            <div><dt>Backend</dt><dd>{health.status}</dd></div>
            <div><dt>Version</dt><dd>{health.version}</dd></div>
            <div><dt>Target</dt><dd>{health.platform_target}</dd></div>
            <div><dt>REW required now</dt><dd>{health.rew_required ? 'yes' : 'no'}</dd></div>
          </dl>
        )}
        {!health && !error && <p>バックエンドを確認しています…</p>}
        {error && <p className="error">Backend unavailable: {error}</p>}
      </section>

      <section className="panel">
        <h2>First validation loop</h2>
        <ol>
          <li>MLPでFL/FRを基準測定</li>
          <li>同条件再測定で測定ばらつきを確認</li>
          <li>配置Aを保存</li>
          <li>一つだけ変更して配置Bを作成</li>
          <li>A/B差と再測定差を比較</li>
        </ol>
      </section>
    </main>
  )
}
