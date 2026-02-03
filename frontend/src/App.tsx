import './App.css'
import { useEffect, useMemo, useRef, useState } from 'react'

import Crosshair from './component/Crosshair'
import Noise from './component/Noise'

type StockRow = {
  id: number
  ticker: string
  name: string
  industry: string | null
  purchase_date: string | null
  purchase_price: number | null
  last_price: number | null
  last_price_at: string | null
  return_abs: number | null
  return_pct: number | null
}

type IndustryRow = {
  id: number
  name: string
  stock_count: number
  avg_return_pct: number | null
}

type Summary = {
  now_utc: string
  stocks: StockRow[]
  industries: IndustryRow[]
}

function fmtMoney(n: number | null): string {
  if (n === null || Number.isNaN(n)) return '--'
  return n.toFixed(2)
}

function fmtPct(n: number | null): string {
  if (n === null || Number.isNaN(n)) return '--'
  const sign = n >= 0 ? '+' : ''
  return `${sign}${n.toFixed(2)}%`
}

function clsForPct(n: number | null): string {
  if (n === null) return ''
  return n >= 0 ? 'pos' : 'neg'
}

function App() {
  const terminalRef = useRef<HTMLDivElement>(null)
  const [summary, setSummary] = useState<Summary | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [selectedTicker, setSelectedTicker] = useState<string | null>(null)
  const [selectedIndustry, setSelectedIndustry] = useState<string | null>(null)
  const [isRefreshing, setIsRefreshing] = useState(false)
  const [isUpdating, setIsUpdating] = useState(false)
  const [isBackfilling, setIsBackfilling] = useState(false)
  const [lastAction, setLastAction] = useState<string | null>(null)

  const stocks = summary?.stocks ?? []
  const industries = summary?.industries ?? []

  const filteredStocks = useMemo(() => {
    if (!selectedIndustry) return stocks
    return stocks.filter((s) => s.industry === selectedIndustry)
  }, [stocks, selectedIndustry])

  const selected = useMemo(() => {
    if (!filteredStocks.length) return null
    if (!selectedTicker) return filteredStocks[0]
    return filteredStocks.find((s) => s.ticker === selectedTicker) ?? filteredStocks[0]
  }, [filteredStocks, selectedTicker])

  async function refresh(): Promise<void> {
    setIsRefreshing(true)
    setError(null)
    try {
      const res = await fetch('/api/summary')
      if (!res.ok) throw new Error(`API ${res.status}`)
      const data = (await res.json()) as Summary
      setSummary(data)
      if (!selectedTicker && data.stocks.length) setSelectedTicker(data.stocks[0].ticker)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load')
    } finally {
      setIsRefreshing(false)
    }
  }

  async function triggerUpdate(): Promise<void> {
    setIsUpdating(true)
    setLastAction(null)
    try {
      const res = await fetch('/api/actions/update', { method: 'POST' })
      const body = (await res.json()) as { ok?: boolean; result?: { updated?: number; skipped?: number; failed?: number } }
      setLastAction(
        `UPDATE updated=${body?.result?.updated ?? 0} skipped=${body?.result?.skipped ?? 0} failed=${body?.result?.failed ?? 0}`,
      )
    } catch (e) {
      setLastAction(`UPDATE failed: ${e instanceof Error ? e.message : 'unknown error'}`)
    } finally {
      setIsUpdating(false)
      await refresh()
    }
  }

  async function triggerBackfill(): Promise<void> {
    setIsBackfilling(true)
    setLastAction(null)
    try {
      const res = await fetch('/api/actions/backfill?only_missing=false', { method: 'POST' })
      const body = (await res.json()) as { ok?: boolean; result?: { inserted?: number; skipped?: number; failed?: number } }
      setLastAction(
        `BACKFILL inserted=${body?.result?.inserted ?? 0} skipped=${body?.result?.skipped ?? 0} failed=${body?.result?.failed ?? 0}`,
      )
    } catch (e) {
      setLastAction(`BACKFILL failed: ${e instanceof Error ? e.message : 'unknown error'}`)
    } finally {
      setIsBackfilling(false)
      await refresh()
    }
  }

  useEffect(() => {
    refresh()
    const id = window.setInterval(refresh, 30_000)
    return () => window.clearInterval(id)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    const onKeyDown = (ev: KeyboardEvent) => {
      if (!filteredStocks.length) return
      if (ev.key !== 'ArrowDown' && ev.key !== 'ArrowUp') return
      ev.preventDefault()
      const idx = Math.max(
        0,
        filteredStocks.findIndex((s) => s.ticker === (selected?.ticker ?? '')),
      )
      const nextIdx =
        ev.key === 'ArrowDown'
          ? Math.min(filteredStocks.length - 1, idx + 1)
          : Math.max(0, idx - 1)
      setSelectedTicker(filteredStocks[nextIdx].ticker)
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [filteredStocks, selected])

  const tape = useMemo(() => {
    const source = selectedIndustry ? filteredStocks : stocks
    const top = source.slice(0, 12)
    // duplicate so we can scroll a seamless loop
    return [...top, ...top]
  }, [stocks, filteredStocks, selectedIndustry])

  useEffect(() => {
    // If the current selection is outside the filtered set, reset to first available.
    if (!selectedIndustry) return
    if (!filteredStocks.length) {
      setSelectedTicker(null)
      return
    }
    if (selectedTicker && filteredStocks.some((s) => s.ticker === selectedTicker)) return
    setSelectedTicker(filteredStocks[0].ticker)
  }, [filteredStocks, selectedIndustry, selectedTicker])

  return (
    <div className="terminal-root" ref={terminalRef}>
      <Noise patternAlpha={12} patternRefreshInterval={2} />
      <Crosshair color="rgba(255, 179, 0, 0.45)" containerRef={terminalRef} />

      <div className="terminal-grid">
        <div className="topbar">
          <div className="brand">IGOUDAR Terminal</div>
          <div className="ticker" aria-label="ticker tape">
            <div className="ticker-track">
              {tape.map((s, i) => (
                <div className="tick" key={`${s.ticker}-${i}`}> 
                  <span className="sym">{s.ticker}</span>
                  <span className={`pct ${s.return_pct !== null && s.return_pct < 0 ? 'neg' : 'pos'}`}>
                    {fmtPct(s.return_pct)}
                  </span>
                  <span className="muted">{s.industry ?? ''}</span>
                </div>
              ))}
            </div>
          </div>
          <button className="btn" onClick={refresh} disabled={isRefreshing}>
            {isRefreshing ? 'REFRESH…' : 'REFRESH'}
          </button>
          <button className="btn" onClick={triggerUpdate} disabled={isUpdating}>
            {isUpdating ? 'UPDATE…' : 'UPDATE'}
          </button>
          <button className="btn" onClick={triggerBackfill} disabled={isBackfilling}>
            {isBackfilling ? 'BACKFILL…' : 'BACKFILL'}
          </button>
        </div>

        <section className="panel left" aria-label="industries">
          <div className="panel-title">
            <div className="label">INDUSTRIES</div>
            <div className="muted">{industries.length}</div>
          </div>
          <div className="panel-body">
            <table className="table">
              <thead>
                <tr>
                  <th>NAME</th>
                  <th className="num">AVG %</th>
                  <th className="num">N</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  className={!selectedIndustry ? 'selected' : ''}
                  onClick={() => setSelectedIndustry(null)}
                  style={{ cursor: 'pointer' }}
                >
                  <td style={{ fontWeight: 700, color: 'var(--cyan)' }}>ALL</td>
                  <td className="num muted">--</td>
                  <td className="num muted">{stocks.length}</td>
                </tr>
                {industries.map((ind) => (
                  <tr
                    key={ind.id}
                    className={selectedIndustry === ind.name ? 'selected' : ''}
                    onClick={() => setSelectedIndustry(ind.name)}
                    style={{ cursor: 'pointer' }}
                  >
                    <td>{ind.name}</td>
                    <td className={`num ${clsForPct(ind.avg_return_pct)}`}>{fmtPct(ind.avg_return_pct)}</td>
                    <td className="num muted">{ind.stock_count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <section className="panel center" aria-label="stocks">
          <div className="panel-title">
            <div className="label">STOCKS{selectedIndustry ? ` / ${selectedIndustry.toUpperCase()}` : ''}</div>
            <div className="muted">{filteredStocks.length}</div>
          </div>
          <div className="panel-body">
            {error ? <div className="muted">ERROR: {error}</div> : null}
            {!error && !summary ? <div className="muted">LOADING…</div> : null}
            <table className="table">
              <thead>
                <tr>
                  <th>TICKER</th>
                  <th className="hide-mobile">NAME</th>
                  <th className="hide-mobile">IND</th>
                  <th className="num hide-mobile">P/L</th>
                  <th className="num">%RTN</th>
                  <th className="num">LAST</th>
                </tr>
              </thead>
              <tbody>
                {filteredStocks.map((s) => (
                  <tr
                    key={s.id}
                    className={selected?.ticker === s.ticker ? 'selected' : ''}
                    onClick={() => setSelectedTicker(s.ticker)}
                    style={{ cursor: 'pointer' }}
                  >
                    <td style={{ fontWeight: 700, color: 'var(--cyan)' }}>{s.ticker}</td>
                    <td className="hide-mobile">{s.name}</td>
                    <td className="muted hide-mobile">{s.industry ?? '--'}</td>
                    <td className={`num hide-mobile ${clsForPct(s.return_abs)}`}>{fmtMoney(s.return_abs)}</td>
                    <td className={`num ${clsForPct(s.return_pct)}`}>{fmtPct(s.return_pct)}</td>
                    <td className="num">{fmtMoney(s.last_price)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <section className="panel right" aria-label="detail">
          <div className="panel-title">
            <div className="label">DETAIL</div>
            <div className="muted">{selected?.ticker ?? '--'}</div>
          </div>
          <div className="panel-body">
            {!selected ? (
              <div className="muted">Select a stock</div>
            ) : (
              <>
                <div style={{ marginBottom: 10 }}>
                  <div style={{ fontSize: 18, fontWeight: 800, color: 'var(--cyan)' }}>{selected.ticker}</div>
                  <div className="muted">{selected.name}</div>
                  <div className="muted">{selected.industry ?? '--'}</div>
                </div>
                <div className="kpi">
                  <div className="box">
                    <div className="name">RETURN %</div>
                    <div className={`val ${clsForPct(selected.return_pct)}`}>{fmtPct(selected.return_pct)}</div>
                  </div>
                  <div className="box">
                    <div className="name">P/L</div>
                    <div className={`val ${clsForPct(selected.return_abs)}`}>{fmtMoney(selected.return_abs)}</div>
                  </div>
                  <div className="box">
                    <div className="name">PURCHASE</div>
                    <div className="val">{fmtMoney(selected.purchase_price)}</div>
                    <div className="muted">{selected.purchase_date ?? '--'}</div>
                  </div>
                  <div className="box">
                    <div className="name">LAST</div>
                    <div className="val">{fmtMoney(selected.last_price)}</div>
                    <div className="muted">{selected.last_price_at ?? '--'}</div>
                  </div>
                </div>
                <div style={{ marginTop: 12 }} className="muted">
                  Tip: use ↑/↓ to change selection.
                </div>
              </>
            )}
          </div>
        </section>

        <div className="statusbar">
          <div>
            {summary?.now_utc ? `NOW(UTC): ${summary.now_utc}` : 'NOW(UTC): --'}
            {selected ? `  |  SEL: ${selected.ticker}` : ''}
            {selectedIndustry ? `  |  FILTER: ${selectedIndustry}` : ''}
            {lastAction ? `  |  ${lastAction}` : ''}
          </div>
          <div>
            API: /api/summary  |  Backend: 127.0.0.1:8000
          </div>
        </div>
      </div>
    </div>
  )
}

export default App
