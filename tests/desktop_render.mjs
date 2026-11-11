// Renders the Desktop half to static HTML against the stub SDK. Run from a folder that holds
// plugin.js, fixtures.json and node_modules with react, react-dom and the stub as @hermes/plugin-sdk.
import { readFileSync } from 'node:fs'
import { createElement as el } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { state } from '@hermes/plugin-sdk'
import plugin from './plugin.js'

const fixtures = JSON.parse(readFileSync(new URL('./fixtures.json', import.meta.url), 'utf8'))
const regs = []
plugin.register({ rest: async () => ({}), register: r => regs.push(r), onDispose() {} })
const by = Object.fromEntries(regs.map(r => [r.id, r]))
const html = id => renderToStaticMarkup(el(() => by[id].render()))
const out = { id: plugin.id, regs: regs.map(r => ({ id: r.id, area: r.area, data: r.data && { path: r.data.path, label: r.data.label, codicon: r.data.codicon, placement: r.data.placement } })) }

state.fixtures = {}
out.loading = html('page')
state.fixtures = { 'pioneer/board': { error: 'HTTP 404' } }
out.down = html('page')
state.fixtures = { 'pioneer/board': { data: { ok: true, empty: true } } }
out.empty = html('pane')
state.fixtures = fixtures
out.page = html('page')
out.pane = html('pane')
out.events = state.sent.filter(s => s[0] === 'onEvent')
process.stdout.write(JSON.stringify(out))
