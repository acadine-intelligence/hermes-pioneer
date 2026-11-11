// Built by scripts/build_desktop.py from desktop_src/plugin.src.js. Edit the source, then rebuild.
// Pioneer: find what does not exist yet and should. Desktop half.
// Backend: /api/plugins/pioneer/* (dashboard/plugin_api.py on the Hermes host). Read-only.
// A round is run by the agent, so every action button sends one plain sentence to the open chat.
// Switches are changed by the user in Settings -> Plugins -> Pioneer (the plugin.yaml config form).
import * as sdk from '@hermes/plugin-sdk'
import { host, useQuery, haptic, Button, Codicon, PALETTE_AREA, ROUTES_AREA, SIDEBAR_NAV_AREA } from '@hermes/plugin-sdk'
import { createContext, createElement as el, useContext, useEffect, useState } from 'react'

const ID = 'pioneer'
const PATH = '/pioneer'
let rest = null

// Colours go through --p-* variables, set once per surface. The pane beside the chat follows the
// app's theme. The Pioneer page carries Pioneer's own look, whatever theme the app is in.
const C = { sec: 'var(--p-sec)', ter: 'var(--p-ter)', line: 'var(--p-line)', acc: 'var(--p-acc)', fg: 'var(--p-fg)' }
const NATIVE = {
  '--p-sec': 'var(--ui-text-secondary)', '--p-ter': 'var(--ui-text-tertiary)', '--p-line': 'var(--ui-stroke-secondary)',
  '--p-acc': 'var(--ui-accent)', '--p-fg': 'var(--foreground, inherit)'
}
const GLASS = {
  '--p-sec': '#c9d8ea', '--p-ter': '#8292a9', '--p-line': 'rgb(136 199 255 / 0.22)', '--p-acc': '#58e6ff', '--p-fg': '#eaf4ff'
}
const INK = '#03050a'
// Empty in the published build. A personal build may inline its own image (scripts/build_desktop.py --art).
const ART = ''
const WORDMARK = 'data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAxNTcgMjgiIGZpbGw9Im5vbmUiIHN0cm9rZT0iI0U4RTlFQyIgc3Ryb2tlLXdpZHRoPSIyIiBzdHJva2UtbGluZWpvaW49Im1pdGVyIiBzdHJva2UtbWl0ZXJsaW1pdD0iMTIiIHJvbGU9ImltZyIgYXJpYS1sYWJlbD0iUGlvbmVlciI+CiAgPCEtLSBXYXlwb2ludDogdGhlIE8gaXMgdGhlIEFjYWRpbmUgbWFyaywgYSByaW5nIG9wZW5lZCBvbiBvbmUgYmVhcmluZyB3aXRoIHRoZSBjeWFuIHdheXBvaW50IGFscmVhZHkgb3V0c2lkZSBpdC4gLS0+CiAgPHBhdGggZD0iTTIgMjZWMmg4YTcgNyAwIDAgMSAwIDE0SDIiLz4KICA8cGF0aCBkPSJNMjUgMnYyNCIvPgogIDxwYXRoIGQ9Ik01Ni40IDhBMTIgMTIgMCAxIDEgNTIgMy42Ii8+CiAgPHBhdGggZD0iTTU4LjIgMCA2MS40IDMuMiA1OC4yIDYuNCA1NSAzLjJ6IiBmaWxsPSIjNThFNkZGIiBzdHJva2U9Im5vbmUiLz4KICA8cGF0aCBkPSJNNjcgMjZWMmwxOCAyNFYyIi8+CiAgPHBhdGggZD0iTTEwOCAySDk0djI0aDE0TTk0IDE0aDExIi8+CiAgPHBhdGggZD0iTTEzMSAyaC0xNHYyNGgxNE0xMTcgMTRoMTEiLz4KICA8cGF0aCBkPSJNMTQxIDI2VjJoOGE3IDcgMCAwIDEgMCAxNGgtOE0xNDggMTZsOCAxMCIvPgo8L3N2Zz4K'
const Look = createContext('native')

const BASE_CSS = `
.pnr-aim{display:flex;align-items:center;gap:8px;min-width:0;flex-wrap:wrap;border:1px solid var(--p-line);border-radius:12px;padding:5px 5px 5px 12px;transition:border-color .2s,box-shadow .2s}
.pnr-aim:focus-within{border-color:var(--p-acc);box-shadow:0 0 0 3px color-mix(in srgb,var(--p-acc) 18%,transparent)}
.pnr-aim span{flex:none;font-size:13px;line-height:18px;color:var(--p-sec);white-space:nowrap}
.pnr-aim input{flex:1 1 120px;min-width:0;background:transparent;border:0;outline:0;color:inherit;font:inherit;font-size:13px;line-height:18px;padding:3px 0}
.pnr-aim input::placeholder{color:var(--p-ter)}
.pnr-skel{border-radius:12px;background:linear-gradient(100deg,var(--p-line) 30%,color-mix(in srgb,var(--p-line) 35%,transparent) 50%,var(--p-line) 70%);background-size:220% 100%;animation:pnr-shimmer 1.3s linear infinite}
@keyframes pnr-shimmer{0%{background-position:120% 0}100%{background-position:-100% 0}}
.pnr-run{position:relative;height:3px;border-radius:999px;background:var(--p-line);overflow:hidden}
.pnr-run::after{content:"";position:absolute;top:0;bottom:0;left:0;width:38%;border-radius:999px;background:linear-gradient(90deg,transparent,var(--p-acc));animation:pnr-slide 1.25s ease-in-out infinite}
@keyframes pnr-slide{0%{transform:translateX(-110%)}100%{transform:translateX(290%)}}
.pnr-live{flex:none;width:8px;height:8px;border-radius:999px;background:var(--p-acc);animation:pnr-pulse 1.4s ease-in-out infinite}
@keyframes pnr-pulse{0%,100%{opacity:.35;transform:scale(.8)}50%{opacity:1;transform:scale(1.15)}}
@media (prefers-reduced-motion:reduce){.pnr-skel,.pnr-run::after,.pnr-live{animation:none}}
`
const GLASS_CSS = `
.pnr-glass .pnr-aim{background:rgb(10 21 40/.55);backdrop-filter:blur(14px) saturate(1.2);-webkit-backdrop-filter:blur(14px) saturate(1.2);box-shadow:inset 0 1px 0 rgb(234 244 255/.10)}
.pnr-btn{font:inherit;font-size:12px;font-weight:600;line-height:18px;padding:5px 12px;border-radius:9px;cursor:pointer;white-space:nowrap;color:#eaf4ff;background:rgb(10 21 40/.55);border:1px solid rgb(136 199 255/.28);transition:transform .15s,box-shadow .2s,border-color .2s,background .2s}
.pnr-btn:hover{transform:translateY(-1px);border-color:#58e6ff;box-shadow:0 0 18px rgb(88 230 255/.22)}
.pnr-btn:active{transform:translateY(0) scale(.98)}
.pnr-btn:focus-visible{outline:2px solid #58e6ff;outline-offset:2px}
.pnr-btn[data-kind=solid]{background:rgb(88 230 255/.13);border-color:rgb(88 230 255/.5)}
.pnr-btn[data-kind=primary]{background:linear-gradient(90deg,#247bff,#58e6ff);border-color:transparent;color:#03050a}
.pnr-btn:disabled{opacity:.45;cursor:default;transform:none;box-shadow:none}
.pnr-glass .pnr-card{background:rgb(10 21 40/.58)!important;border:1px solid rgb(136 199 255/.22)!important;border-radius:14px!important;backdrop-filter:blur(14px) saturate(1.2);-webkit-backdrop-filter:blur(14px) saturate(1.2);box-shadow:inset 0 1px 0 rgb(234 244 255/.10),0 0 32px rgb(88 230 255/.06);transition:border-color .2s,box-shadow .2s}
.pnr-glass .pnr-card:hover{border-color:rgb(136 199 255/.42)!important}
.pnr-glass .pnr-card[data-hot]{border-color:rgb(88 230 255/.6)!important;box-shadow:inset 0 1px 0 rgb(234 244 255/.12),0 0 36px rgb(88 230 255/.14)}
.pnr-glass .pnr-score{font-size:24px!important;line-height:24px;color:#58e6ff;letter-spacing:-.02em}
.pnr-glass .pnr-fill{background:linear-gradient(90deg,#247bff,#58e6ff)!important}
.pnr-art{position:absolute;inset:0;z-index:0;pointer-events:none;background:no-repeat right -2% top 10%/auto 112%;opacity:.5;-webkit-mask-image:linear-gradient(to right,transparent 38%,#000 72%),linear-gradient(to bottom,transparent 0,#000 14%,#000 72%,transparent 100%);-webkit-mask-composite:source-in;mask-image:linear-gradient(to right,transparent 38%,#000 72%),linear-gradient(to bottom,transparent 0,#000 14%,#000 72%,transparent 100%);mask-composite:intersect;animation:pnr-breathe 8s ease-in-out infinite}
@keyframes pnr-breathe{0%,100%{opacity:.44}50%{opacity:.58}}
@media (max-width:900px){.pnr-art{opacity:.2;animation:none}}
.pnr-way{position:absolute;right:-150px;top:-90px;width:760px;height:760px;z-index:0;pointer-events:none;-webkit-mask-image:radial-gradient(closest-side,#000 50%,transparent 100%);mask-image:radial-gradient(closest-side,#000 50%,transparent 100%)}
.pnr-orbit{transform-origin:300px 300px;animation:pnr-spin 120s linear infinite}
.pnr-busy .pnr-orbit{animation-duration:9s;stroke-opacity:.7}
.pnr-dot{transform-box:fill-box;transform-origin:center;animation:pnr-pulse 3.4s ease-in-out infinite;filter:drop-shadow(0 0 8px #58e6ff)}
.pnr-busy .pnr-dot{animation-duration:1.2s}
@keyframes pnr-spin{to{transform:rotate(360deg)}}
@media (max-width:900px){.pnr-way{opacity:.35}}
@media (prefers-reduced-motion:reduce){.pnr-art,.pnr-orbit,.pnr-dot{animation:none}.pnr-btn{transition:none}.pnr-btn:hover{transform:none}}
`
const VERDICT = {
  pioneer: 'pioneer', iterate: 'iterate', beat: 'beat it', unchecked: 'not checked', park: 'park', adopt: 'use existing'
}
const BARS = [['need', 'Need'], ['originality', 'Original'], ['counterfactual', 'Counter'], ['value', 'Value'], ['durability', 'Durable']]
const LIVE = { pioneer: 1, iterate: 1, beat: 1 }
const SAFE_GAP = /^r\d{1,6}\.g\d{1,4}$/

// ---- data ----------------------------------------------------------------------------------------

function unwrap(r) {
  const body = r && typeof r === 'object' && 'ok' in r ? r : r?.data ?? r
  if (!body) throw new Error('no response')
  if (body.ok !== true) throw new Error(body.error || 'request failed')
  return body
}

function useBoard() {
  return useQuery({
    queryKey: [ID, 'board'],
    queryFn: async () => {
      if (!rest) throw new Error('backend not ready')
      return unwrap(await rest('/board'))
    },
    refetchInterval: 6_000,
    staleTime: 5_000,
    retry: 1
  })
}

function useGap(id, on) {
  return useQuery({
    queryKey: [ID, 'gap', id],
    enabled: !!on && SAFE_GAP.test(id),
    queryFn: async () => unwrap(await rest(`/gap/${id}`)),
    staleTime: 5_000,
    retry: 1
  })
}

function useSetup(on) {
  return useQuery({
    queryKey: [ID, 'setup'],
    enabled: !!on,
    queryFn: async () => unwrap(await rest('/setup')).setup,
    staleTime: 30_000,
    retry: 1
  })
}

// Send one sentence to a chat. A chat on screen gets it (the pane sits beside one). The Pioneer page
// has no chat on screen, so there the request starts a fresh chat and is sent in it. Only when the
// app cannot do either is the request copied instead.
// "Something is running": set when a request reaches a chat, until the round shows up in the trail.
let pendingAt = 0
const pendingSubs = new Set()
function setPending(at) {
  pendingAt = at
  pendingSubs.forEach(fn => fn())
}
function usePending() {
  const [, tick] = useState(0)
  useEffect(() => {
    const fn = () => tick(n => n + 1)
    pendingSubs.add(fn)
    const timer = setInterval(fn, 5000)
    return () => {
      pendingSubs.delete(fn)
      clearInterval(timer)
    }
  }, [])
  return pendingAt > 0 && Date.now() - pendingAt < 90_000
}

const sleep = ms => new Promise(resolve => setTimeout(resolve, ms))
let asking = false

function send(address, prompt) {
  try {
    return host.composer?.submit?.(address, prompt) === true
  } catch {
    return false
  }
}

async function ask(prompt) {
  haptic('tap')
  if (asking) return
  asking = true
  try {
    if (send(null, prompt)) {
      host.notify({ kind: 'success', message: 'Sent to the chat' })
      setPending(Date.now())
      return
    }
    if (typeof host.newChat === 'function') {
      try {
        host.newChat()
      } catch {
        /* an older app: fall through to the copy */
      }
      // The fresh chat takes a moment to mount. submit() refuses until its composer is on screen.
      for (let i = 0; i < 30; i += 1) {
        await sleep(150)
        if (send('new', prompt)) {
          host.notify({ kind: 'success', message: 'Started a new chat with it' })
          setPending(Date.now())
          return
        }
      }
    }
    try {
      await navigator.clipboard?.writeText(prompt)
    } catch {
      /* clipboard unavailable: the message below still says what to do */
    }
    host.notify({ kind: 'info', message: 'Could not open a chat. The request is on your clipboard: paste it into a chat.' })
  } finally {
    asking = false
  }
}

function Btn({ variant, size, kind, children, ...rest }) {
  const look = useContext(Look)
  if (look !== 'glass') return el(Button, { variant, size, ...rest }, children)
  return el('button', { type: 'button', className: 'pnr-btn', 'data-kind': kind || (variant === 'outline' ? 'quiet' : 'solid'), ...rest }, children)
}

// A pasted copy of the whole request is reduced to its aim, so the sentence is never doubled.
function cleanAim(raw) {
  return String(raw || '').replace(/\s+/g, ' ').trim()
    .replace(/^(?:(?:run pioneer on this workspace[.!]?|what should exist for)\s*)+/i, '')
    .replace(/[?.!\s]+$/, '').slice(0, 200)
}

// The aim of a round, in the user's words. A round with no aim returns generic gaps, so there is
// no bare "run" button: the field is the way in.
function Aim() {
  const [aim, setAim] = useState('')
  const text = cleanAim(aim)
  const go = () => {
    if (!text) return
    ask(`Run pioneer on this workspace. What should exist for ${text}?`)
    setAim('')
  }
  return el('div', { className: 'pnr-aim', style: { flex: '1 1 300px', maxWidth: 560 } },
    el('span', null, 'What should exist for'),
    el('input', {
      value: aim, maxLength: 200, 'aria-label': 'What should exist for', placeholder: 'an operator running a fleet of agents',
      onChange: e => setAim(e.target.value), onKeyDown: e => { if (e.key === 'Enter') { e.preventDefault(); go() } }
    }),
    el(Btn, { size: 'sm', kind: 'primary', disabled: !text, onClick: go }, 'Run'))
}

function roundOf(gapId) {
  return String(gapId).split('.')[0]
}

function num(v) {
  return v === null || v === undefined ? '?' : String(v)
}

// ---- small parts ---------------------------------------------------------------------------------

function Chip({ children, hot }) {
  return el('span', {
    style: {
      flex: 'none', fontSize: 11, lineHeight: '16px', padding: '0 8px', borderRadius: 999, whiteSpace: 'nowrap',
      border: `1px solid ${hot ? C.acc : C.line}`, color: hot ? C.acc : C.sec
    }
  }, children)
}

function Bar({ label, value }) {
  const [w, setW] = useState(0)
  useEffect(() => {
    setW(value === null || value === undefined ? 0 : Math.max(0, Math.min(100, Number(value) || 0)))
  }, [value])
  return el('div', { style: { minWidth: 0 } },
    el('div', { style: { display: 'flex', justifyContent: 'space-between', gap: 4, fontSize: 11, lineHeight: '16px' } },
      el('span', { style: { color: C.ter, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' } }, label),
      el('span', { style: { fontVariantNumeric: 'tabular-nums' } }, num(value))),
    el('div', { style: { height: 4, borderRadius: 999, background: C.line, overflow: 'hidden', marginTop: 3 } },
      el('div', { className: 'pnr-fill', style: { height: '100%', width: `${w}%`, borderRadius: 999, background: C.acc, transition: 'width .7s ease-out' } })))
}

// Originality across, need up. A gap with no absence check has no originality, so it is not drawn.
function Chart({ gaps, win, onPick }) {
  const W = 240, H = 176, P = 24
  const x = v => P + ((W - P - 10) * v) / 100
  const y = v => H - P - ((H - P - 10) * v) / 100
  const zone = win || { originality: 70, need: 70 }
  return el('svg', {
    width: W, height: H, viewBox: `0 0 ${W} ${H}`, role: 'img', 'aria-label': 'Originality against need', className: 'pnr-card',
    style: { flex: 'none', border: `1px solid ${C.line}`, borderRadius: 10 }
  },
    el('rect', {
      x: x(zone.originality), y: y(100), width: x(100) - x(zone.originality), height: y(zone.need) - y(100),
      rx: 4, style: { fill: C.acc, opacity: 0.13 }
    }),
    el('text', { x: W / 2, y: H - 7, textAnchor: 'middle', style: { fill: C.ter, fontSize: 9 } }, 'originality'),
    el('text', { x: 10, y: H / 2, textAnchor: 'middle', transform: `rotate(-90 10 ${H / 2})`, style: { fill: C.ter, fontSize: 9 } }, 'need'),
    gaps.map((g, i) => g.originality === null || g.originality === undefined ? null :
      el('g', { key: g.id, style: { cursor: 'pointer' }, onClick: () => onPick(g.id) },
        el('title', null, g.title),
        el('circle', {
          cx: x(g.originality), cy: y(g.need), r: 9,
          style: { fill: 'none', strokeWidth: 1.5, stroke: LIVE[g.verdict] ? C.acc : C.ter }
        }),
        el('text', { x: x(g.originality), y: y(g.need) + 3, textAnchor: 'middle', style: { fill: 'currentColor', fontSize: 9, fontWeight: 600 } }, String(i + 1)))))
}

function Detail({ id }) {
  const q = useGap(id, true)
  if (q.isLoading) return el('div', { className: 'pnr-skel', 'aria-busy': true, style: { height: 44, marginTop: 10 } })
  if (q.isError) return el('div', { style: { fontSize: 12, color: C.sec, marginTop: 10 } }, String(q.error?.message || q.error))
  const g = q.data.gap || {}
  const ab = g.absence
  const shown = ab ? (ab.candidates || []).filter(c => c.ruling && c.ruling !== 'unrelated') : []
  const others = ab ? (ab.candidates || []).length - shown.length : 0
  const head = { fontSize: 11, color: C.ter, margin: '10px 0 4px' }
  const row = { fontSize: 12, lineHeight: '18px', color: C.sec, overflowWrap: 'anywhere' }
  const link = (url, text) => /^https?:\/\//.test(url || '')
    ? el('a', { href: url, target: '_blank', rel: 'noreferrer', style: { color: 'inherit', textDecoration: 'underline' } }, text)
    : text
  return el('div', { style: { borderTop: `1px solid ${C.line}`, marginTop: 10 } },
    el('div', { style: head }, `For ${g.buyer || 'no buyer named'}. New part: ${g.mechanism || 'not stated'}`),
    el('div', { style: head }, 'Ratings by the model, 1 to 5'),
    Object.entries(g.ratings || {}).map(([dim, r]) =>
      el('div', { key: dim, style: row }, `${dim} ${r.n}/5${r.why ? `: ${r.why}` : ''}`)),
    el('div', { style: head }, `Evidence (${(q.data.evidence || []).length} signals)`),
    (q.data.evidence || []).map(e =>
      el('div', { key: e.id, style: row }, `${e.id} ${e.src} · ${e.kind}: `, link(e.url, e.title))),
    ab
      ? el('div', null,
          el('div', { style: head },
            `Absence check: ${(ab.queries || []).length} searches, answered by ${(ab.sources_ok || []).join(', ') || 'nothing'}` +
            (ab.judge ? ` · judge ${ab.judge.backend}` : '')),
          shown.map(c =>
            el('div', { key: c.id, style: row },
              `${c.ruling}${c.judge_p === null || c.judge_p === undefined ? '' : ` (judge ${c.judge_p})`}: `,
              link(c.url, c.title), c.why ? `. ${c.why}` : '')),
          el('div', { style: { ...row, color: C.ter } },
            shown.length === 0 ? `No existing tool covers it. ${others} looked at and ruled unrelated.` : `${others} more ruled unrelated.`))
      : el('div', { style: head }, 'No absence check yet, so originality is not measured.'))
}

function GapCard({ g, n, open, onToggle, compact }) {
  const safe = SAFE_GAP.test(g.id)
  return el('div', {
    id: `pioneer-gap-${g.id}`, className: 'pnr-card', 'data-hot': g.verdict === 'pioneer' ? '' : undefined,
    style: { border: `1px solid ${g.verdict === 'pioneer' ? C.acc : C.line}`, borderRadius: 10, padding: compact ? 10 : 12 }
  },
    el('div', { style: { display: 'flex', alignItems: 'baseline', gap: 8 } },
      el('span', { style: { flex: 'none', color: C.ter, fontSize: 12, fontVariantNumeric: 'tabular-nums' } }, String(n)),
      el('span', { title: g.id, style: { flex: 1, minWidth: 0, fontSize: 13, fontWeight: 600, lineHeight: '18px' } }, g.title),
      el(Chip, { hot: g.verdict === 'pioneer' }, VERDICT[g.verdict] || g.verdict),
      el('span', { className: 'pnr-score', style: { flex: 'none', fontSize: 13, fontWeight: 600, fontVariantNumeric: 'tabular-nums' } }, num(g.pioneer))),
    !compact && el('div', { style: { fontSize: 12, lineHeight: '18px', marginTop: 4 } }, g.one_line),
    el('div', { style: { fontSize: 12, lineHeight: '18px', color: C.sec, marginTop: 3 } },
      g.line),
    el('div', { style: { display: 'grid', gridTemplateColumns: 'repeat(5, minmax(0, 1fr))', gap: compact ? 6 : 10, marginTop: 9 } },
      BARS.map(([key, label]) => el(Bar, { key, label, value: g[key] }))),
    el('div', { style: { display: 'flex', alignItems: 'center', gap: 6, marginTop: 10, flexWrap: 'wrap' } },
      el('span', { style: { flex: 1, minWidth: 120, display: 'flex', gap: 6, flexWrap: 'wrap' } },
        el(Chip, null, `${g.evidence} signals`),
        g.judge_exists === null || g.judge_exists === undefined ? null : el(Chip, null, `judge ${g.judge_exists}`),
        g.thin_check ? el(Chip, null, 'thin search') : null),
      safe && g.verdict === 'unchecked' &&
        el(Btn, { size: 'sm', onClick: () => ask(`Run the Pioneer absence check on gap ${named(g)}.`) }, 'Check it exists'),
      safe && LIVE[g.verdict] &&
        el(Btn, { size: 'sm', onClick: () => ask(`Expand Pioneer gap ${named(g)} into a new round.`) }, 'Expand'),
      el(Btn, { size: 'sm', variant: 'outline', 'aria-expanded': !!open, onClick: () => { haptic('tap'); onToggle(g.id) } },
        open ? 'Hide evidence' : 'Evidence')),
    open && safe && el(Detail, { id: g.id }))
}

// ---- rounds rail ---------------------------------------------------------------------------------

function depthOf(round, byId) {
  let d = 0, cur = round
  while (cur && cur.from && d < 8) {
    cur = byId[roundOf(cur.from)]
    d += 1
  }
  return d
}

function Rounds({ rounds, picked, onPick }) {
  const byId = Object.fromEntries(rounds.map(r => [r.id, r]))
  const item = (key, label, sub, depth, on) =>
    el('button', {
      key, type: 'button', 'aria-pressed': on, onClick: () => { haptic('tap'); onPick(key === 'all' ? null : key) },
      style: {
        display: 'block', width: '100%', textAlign: 'left', cursor: 'pointer', background: 'transparent', color: 'inherit',
        border: 'none', borderLeft: `2px solid ${on ? C.acc : 'transparent'}`,
        padding: `6px 8px 6px ${10 + depth * 14}px`, borderRadius: 4
      }
    },
      el('div', { style: { fontSize: 12, lineHeight: '18px', fontWeight: on ? 600 : 400 } }, label),
      el('div', { style: { fontSize: 11, lineHeight: '16px', color: sub.endsWith('gaps') ? C.ter : C.acc } }, sub))
  const gaps = rounds.reduce((a, r) => a + r.gaps, 0)
  return el('div', { style: { flex: 'none', width: 220, display: 'flex', flexDirection: 'column', gap: 2 } },
    item('all', 'All rounds', `${gaps} gaps`, 0, picked === null),
    rounds.map(r => item(r.id, r.title || `Round ${r.id.slice(1)}`,
      r.running ? STAGE[r.stage] || 'Running' : `${r.gaps} gaps`, depthOf(r, byId), picked === r.id)))
}

// ---- setup ---------------------------------------------------------------------------------------

function settingsHref() {
  return typeof sdk.pluginSettingsHref === 'function' ? sdk.pluginSettingsHref(ID) : `/settings?tab=plugins&plugin=${ID}`
}

function Setup() {
  const q = useSetup(true)
  if (q.isLoading) return el('div', { style: { fontSize: 12, color: C.sec } }, 'Reading what this install has…')
  if (q.isError) return el('div', { style: { fontSize: 12, color: C.sec } }, String(q.error?.message || q.error))
  const s = q.data
  const head = { fontSize: 12, fontWeight: 600, margin: '14px 0 6px' }
  return el('div', { style: { display: 'flex', flexDirection: 'column' } },
    el('div', { style: { display: 'flex', alignItems: 'center', gap: 8 } },
      el('div', { style: { flex: 1, fontSize: 12, lineHeight: '18px', color: C.sec } },
        'You own every switch. The agent can read them and recommend. It cannot change them.'),
      el(Btn, { size: 'sm', onClick: () => { haptic('tap'); host.navigate(settingsHref()) } }, 'Change switches')),
    (s.recommended || []).length > 0 && el('div', { style: head }, 'Recommended for this install'),
    (s.recommended || []).map((r, i) =>
      el('div', { key: i, className: 'pnr-card', style: { border: `1px solid ${C.line}`, borderRadius: 10, padding: 10, marginBottom: 6 } },
        el('div', { style: { fontSize: 13, fontWeight: 600, lineHeight: '18px' } }, `${i + 1}. ${r.do}`),
        el('div', { style: { fontSize: 12, lineHeight: '18px', color: C.sec, marginTop: 2 } }, r.why),
        el('div', { style: { fontSize: 11, lineHeight: '16px', color: C.ter, marginTop: 4, overflowWrap: 'anywhere' } }, `How: ${r.how}`))),
    el('div', { style: head }, 'Options'),
    (s.options || []).map(o =>
      el('div', { key: o.id, style: { display: 'flex', gap: 10, alignItems: 'flex-start', padding: '8px 0', borderTop: `1px solid ${C.line}` } },
        el('div', { style: { flex: 1, minWidth: 0 } },
          el('div', { style: { fontSize: 13, lineHeight: '18px' } }, o.title),
          el('div', { style: { fontSize: 12, lineHeight: '18px', color: C.sec } }, o.adds),
          el('div', { style: { fontSize: 11, lineHeight: '16px', color: C.ter } },
            `Sends: ${o.sends}. Cost: ${o.cost}.${o.ready ? '' : ` Needs ${o.needs}.`}`)),
        el(Chip, { hot: o.state !== 'off' }, String(o.state)))),
    el('div', { style: head }, 'Tools your agent can feed Pioneer with'),
    (s.companions || []).map(c =>
      el('div', { key: c.id, style: { fontSize: 12, lineHeight: '18px', color: C.sec, padding: '3px 0' } },
        el('span', { style: { color: C.fg } }, c.title),
        (c.you_have || []).length ? ` (you have ${c.you_have.join(', ')})` : '', `. ${c.use}`)))
}

// ---- states --------------------------------------------------------------------------------------

function Empty({ withAim }) {
  return el('div', { style: { display: 'flex', flexDirection: 'column', gap: 8, alignItems: 'stretch', padding: 4, maxWidth: 560 } },
    el('div', { style: { fontSize: 13, fontWeight: 600 } }, 'No rounds yet'),
    el('div', { style: { fontSize: 12, lineHeight: '18px', color: C.sec } },
      'A round reads your project folder, memory and recent chats, then looks for what does not exist yet and should. ' +
      (withAim ? 'Say who it is for.' : 'Say who it is for in the field above.')),
    withAim && el(Aim, {}))
}

function Down({ q }) {
  return el('div', { style: { display: 'flex', flexDirection: 'column', gap: 8, alignItems: 'flex-start', padding: 4 } },
    el('div', { style: { fontSize: 13, fontWeight: 600 } }, 'Pioneer backend unavailable'),
    el('div', { style: { fontSize: 12, lineHeight: '18px', color: C.sec } }, String(q.error?.message || q.error)),
    el('div', { style: { fontSize: 11, lineHeight: '16px', color: C.ter } },
      'On the Hermes host: hermes plugins enable pioneer, then restart the gateway.'),
    el(Btn, { size: 'sm', variant: 'outline', onClick: () => q.refetch() }, 'Retry'))
}

const STAGE = { reading: 'Reading the workspace', searching: 'Searching for signals', checking: 'Checking what already exists' }
const plain = text => String(text || '').replace(/["\n\r]+/g, ' ').replace(/\s+/g, ' ').trim().slice(0, 80)
// Requests name the gap by its title. The id rides along for the tool call.
const named = g => `${g.id} ("${plain(g.title)}")`

function Skeleton() {
  return el('div', { 'aria-busy': true, 'aria-label': 'Loading', style: { display: 'flex', flexDirection: 'column', gap: 8 } },
    [0, 1, 2].map(i => el('div', { key: i, className: 'pnr-skel', style: { height: 92, animationDelay: `${i * 0.15}s` } })))
}

function Running({ run }) {
  return el('div', { className: 'pnr-card', role: 'status', style: { border: `1px solid ${C.line}`, borderRadius: 10, padding: '10px 12px', marginBottom: 12 } },
    el('div', { style: { display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 } },
      el('span', { className: 'pnr-live' }),
      el('span', { style: { flex: 'none', fontSize: 13, fontWeight: 600, lineHeight: '18px' } }, run ? STAGE[run.stage] || 'Running' : 'Starting a round'),
      run && el('span', { style: { flex: 1, minWidth: 0, fontSize: 12, lineHeight: '18px', color: C.sec, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' } }, run.title)),
    el('div', { className: 'pnr-run' }))
}

function Tiles({ gaps }) {
  const counts = {}
  gaps.forEach(g => { counts[g.verdict] = (counts[g.verdict] || 0) + 1 })
  const order = ['pioneer', 'iterate', 'beat', 'unchecked', 'park', 'adopt'].filter(k => counts[k])
  return el('div', { style: { flex: 1, minWidth: 200, display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(96px, 1fr))', gap: 8, alignContent: 'start' } },
    order.map(k => el('div', { key: k, className: 'pnr-card', 'data-hot': k === 'pioneer' ? '' : undefined, style: { border: `1px solid ${C.line}`, borderRadius: 10, padding: '10px 12px' } },
      el('div', { className: 'pnr-score', style: { fontSize: 20, fontWeight: 600, lineHeight: '24px', fontVariantNumeric: 'tabular-nums' } }, String(counts[k])),
      el('div', { style: { fontSize: 11, lineHeight: '16px', color: C.sec, marginTop: 4 } }, VERDICT[k] || k))))
}

// The page background: the Pioneer mark, an open ring with the waypoint already outside it. The
// orbit turns slowly, and faster while a round runs.
function Waypoint() {
  return el('svg', { className: 'pnr-way', viewBox: '0 0 600 600', 'aria-hidden': true },
    [110, 175, 250, 292].map(r => el('circle', { key: r, cx: 300, cy: 300, r, fill: 'none', stroke: '#88c7ff', strokeOpacity: 0.09, strokeWidth: 1 })),
    el('circle', { className: 'pnr-orbit', cx: 300, cy: 300, r: 215, fill: 'none', stroke: '#58e6ff', strokeOpacity: 0.3, strokeWidth: 1.2, strokeDasharray: '2 16', strokeLinecap: 'round' }),
    el('path', { d: 'M 392 208 A 130 130 0 1 1 353 181', fill: 'none', stroke: '#eaf4ff', strokeOpacity: 0.2, strokeWidth: 2.5, strokeLinecap: 'round' }),
    el('circle', { className: 'pnr-dot', cx: 400, cy: 157, r: 7, fill: '#58e6ff' }))
}

function Backdrop() {
  if (ART) return el('div', { className: 'pnr-art', 'aria-hidden': true, style: { backgroundImage: `url("${ART}")` } })
  return el(Waypoint, {})
}

function countsLine(gaps) {
  const counts = {}
  gaps.forEach(g => { counts[g.verdict] = (counts[g.verdict] || 0) + 1 })
  return Object.entries(counts).map(([k, n]) => `${n} ${VERDICT[k] || k}`).join(' · ') || 'no gaps yet'
}

function Foot({ b }) {
  const failed = (b.errors || []).length
  const w = b.weights || {}
  return el('div', { style: { marginTop: 'auto', paddingTop: 14 } },
    el('div', { role: 'img', 'aria-label': 'How the score is weighted', style: { display: 'flex', gap: 3 } },
      BARS.map(([key, label]) => el('div', { key, style: { flex: Number(w[key]) || 1, minWidth: 0 } },
        el('div', { className: 'pnr-fill', style: { height: 3, borderRadius: 999, background: C.acc, opacity: 0.55 } }),
        el('div', { style: { fontSize: 10, lineHeight: '14px', color: C.ter, marginTop: 3, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' } }, `${label} ${num(w[key])}`)))),
    failed > 0 && el('div', { style: { marginTop: 8 } }, el(Chip, null, `${failed} searches failed`)))
}

// ---- page and pane -------------------------------------------------------------------------------

function Cards({ gaps, compact }) {
  const [open, setOpen] = useState(null)
  return el('div', { style: { display: 'flex', flexDirection: 'column', gap: 8 } },
    gaps.map((g, i) => el(GapCard, {
      key: g.id, g, n: i + 1, compact, open: open === g.id, onToggle: id => setOpen(open === id ? null : id)
    })))
}

function PioneerPage() {
  const q = useBoard()
  const pending = usePending()
  let busy = pending
  const [tab, setTab] = useState('board')
  const [picked, setPicked] = useState(null)
  const wrap = { position: 'relative', zIndex: 1, height: '100%', overflowY: 'auto', padding: 16, boxSizing: 'border-box' }
  // The column sits left of centre on a wide window, so her face and flag hand stay clear of the cards.
  const inner = {
    maxWidth: 880, minHeight: '100%', margin: '0 auto 0 max(0px, calc((100% - 1000px) * 0.25))',
    display: 'flex', flexDirection: 'column'
  }
  const tabBtn = (key, label) =>
    el(Btn, { key, size: 'sm', variant: tab === key ? undefined : 'outline', 'aria-pressed': tab === key,
      onClick: () => { haptic('tap'); setTab(key) } }, label)
  const header = () =>
    el('div', { style: { display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16, flexWrap: 'wrap' } },
      el('div', { style: { flex: 'none', minWidth: 170 } },
        el('img', { src: WORDMARK, alt: 'Pioneer', style: { display: 'block', height: 18, filter: 'drop-shadow(0 0 10px rgb(88 230 255 / 0.25))' } })),
      el(Aim, {}),
      el('div', { style: { display: 'flex', gap: 6, marginLeft: 'auto' } }, tabBtn('board', 'Board'), tabBtn('setup', 'Setup')))
  let body
  if (tab === 'setup') {
    body = el(Setup, {})
  } else if (q.isLoading) {
    body = el(Skeleton, {})
  } else if (q.isError) {
    body = el(Down, { q })
  } else if (q.data.empty) {
    body = pending ? el(Running, {}) : el(Empty, {})
  } else {
    const b = q.data.board
    const rounds = b.rounds || []
    const live = picked && rounds.some(r => r.id === picked) ? picked : null
    const gaps = (b.gaps || []).filter(g => !live || roundOf(g.id) === live)
    const run = rounds.find(r => r.running)
    busy = !!run || pending
    const pick = id => document.getElementById(`pioneer-gap-${id}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' })
    body = el('div', { style: { display: 'flex', gap: 20, alignItems: 'flex-start', flex: 1 } },
      el(Rounds, { rounds, picked: live, onPick: setPicked }),
      el('div', { style: { flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', minHeight: '100%' } },
        busy && el(Running, { run }),
        el('div', { style: { display: 'flex', gap: 12, alignItems: 'stretch', marginBottom: 12, flexWrap: 'wrap' } },
          el(Chart, { gaps, win: b.win_zone, onPick: pick }),
          el(Tiles, { gaps })),
        gaps.length ? el(Cards, { gaps }) : busy ? el(Skeleton, {}) : el('div', { style: { fontSize: 12, color: C.sec } }, 'No gaps in this round yet.'),
        el(Foot, { b })))
  }
  const root = {
    ...GLASS, position: 'relative', isolation: 'isolate', height: '100%', overflow: 'hidden', color: '#eaf4ff',
    background: `radial-gradient(900px 500px at 15% -10%, rgb(36 123 255 / 0.20), transparent 60%), ${INK}`
  }
  return el(Look.Provider, { value: 'glass' },
    el('div', { className: busy ? 'pnr-glass pnr-busy' : 'pnr-glass', style: root },
      el('style', null, BASE_CSS + GLASS_CSS),
      el(Backdrop, {}),
      el('div', { style: wrap }, el('div', { style: inner }, header(), body))))
}

function PaneBody() {
  const q = useBoard()
  const [all, setAll] = useState(false)
  const wrap = { height: '100%', overflowY: 'auto', padding: 12, boxSizing: 'border-box', display: 'flex', flexDirection: 'column', gap: 10 }
  if (q.isLoading) return el('div', { style: wrap }, el(Skeleton, {}))
  if (q.isError) return el('div', { style: wrap }, el(Down, { q }))
  if (q.data.empty) return el('div', { style: wrap }, el(Empty, { withAim: true }))
  const b = q.data.board
  const latest = b.round
  const rounds = b.rounds || []
  const run = rounds.find(r => r.running)
  const latestTitle = (rounds.find(r => r.id === latest) || {}).title || `Round ${String(latest).slice(1)}`
  const gaps = (b.gaps || []).filter(g => all || roundOf(g.id) === latest)
  return el('div', { style: wrap },
    el('div', { style: { display: 'flex', alignItems: 'center', gap: 6 } },
      el('div', { style: { flex: 1, minWidth: 0 } },
        el('div', { style: { fontSize: 13, fontWeight: 600, lineHeight: '18px' } }, all ? 'All rounds' : latestTitle),
        el('div', { style: { fontSize: 11, lineHeight: '16px', color: C.ter } }, countsLine(gaps))),
      el(Btn, { size: 'sm', variant: 'outline', 'aria-pressed': all, onClick: () => { haptic('tap'); setAll(!all) } },
        all ? 'Latest' : 'All rounds'),
      el(Btn, { size: 'sm', variant: 'outline', onClick: () => host.navigate(PATH) }, 'Open')),
    run && el(Running, { run }),
    gaps.length ? el(Cards, { gaps, compact: true }) : run ? el(Skeleton, {}) : el('div', { style: { fontSize: 12, color: C.sec } }, 'No gaps in this round yet.'),
    el(Foot, { b }))
}

function PioneerPane() {
  return el('div', { style: { ...NATIVE, height: '100%' } }, el('style', null, BASE_CSS), el(PaneBody, {}))
}

// For the tests only. The app reads the default export.
export const __test = { ask, cleanAim }

export default {
  id: ID,
  name: 'Pioneer',
  register(ctx) {
    rest = ctx.rest
    ctx.register({ id: 'page', area: ROUTES_AREA, data: { path: PATH }, render: () => el(PioneerPage, {}) })
    ctx.register({ id: 'nav', area: SIDEBAR_NAV_AREA, data: { path: PATH, label: 'Pioneer', codicon: 'compass' } })
    ctx.register({ id: 'pane', area: 'panes', title: 'Pioneer', data: { placement: 'right', width: '380px' }, render: () => el(PioneerPane, {}) })
    ctx.register({
      id: 'open',
      area: PALETTE_AREA,
      data: { id: 'pioneer.open', label: 'Pioneer: open the board', keywords: ['pioneer', 'gaps', 'ideas', 'original', 'board'], run: () => host.navigate(PATH) }
    })
    // The agent's pioneer tools announce every change, so an open board follows a round as it runs.
    // The 20 s poll in useBoard stays as the fallback.
    if (typeof host.onEvent === 'function' && sdk.queryClient) {
      const stop = host.onEvent(`plugin.${ID}.trail.updated`, () => sdk.queryClient.invalidateQueries({ queryKey: [ID] }))
      if (typeof stop === 'function' && typeof ctx.onDispose === 'function') ctx.onDispose(stop)
    }
  }
}
