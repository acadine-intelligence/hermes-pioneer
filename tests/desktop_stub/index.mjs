// A stand-in for @hermes/plugin-sdk, used only by tests. It records what the plugin registers and
// sends, and answers useQuery from fixtures keyed by the query key.
import { createElement as el } from 'react'

const g = globalThis
// chat: is a chat on screen (submit to the active composer works). newChatAfter: how many submit
// tries the fresh chat needs before its composer is on screen; -1 means it never appears.
g.__PIONEER_TEST__ ||= { fixtures: {}, sent: [], chat: true, newChatAfter: 2, opened: false, tries: 0 }
export const state = g.__PIONEER_TEST__

export const host = {
  notify: m => state.sent.push(['notify', m.kind, m.message]),
  navigate: p => state.sent.push(['navigate', p]),
  // Same contract as the app: submit refuses (false, nothing sent) when no composer for the address
  // is on screen. A full plugin page has no chat on screen.
  composer: {
    submit: (address, text) => {
      if (address === null) {
        if (state.chat) state.sent.push(['submit', 'active', text])
        return state.chat
      }
      if (address !== 'new' || !state.opened || state.newChatAfter < 0) return false
      state.tries += 1
      if (state.tries <= state.newChatAfter) return false
      state.sent.push(['submit', 'new', text])
      return true
    }
  },
  newChat: () => { state.opened = true; state.tries = 0; state.sent.push(['newChat']) },
  onEvent: name => { state.sent.push(['onEvent', name]); return () => {} }
}
export function useQuery({ queryKey, enabled }) {
  if (enabled === false) return { isLoading: false, isError: false, data: undefined, refetch() {} }
  const f = state.fixtures[queryKey.join('/')]
  if (!f) return { isLoading: true, isError: false, refetch() {} }
  if (f.error) return { isLoading: false, isError: true, error: new Error(f.error), refetch() {} }
  return { isLoading: false, isError: false, data: f.data, refetch() {} }
}
export const queryClient = { invalidateQueries() {} }
export const haptic = () => {}
export const Button = ({ children, variant, size, ...rest }) =>
  el('button', { type: 'button', 'data-variant': variant || 'default', ...rest }, children)
export const Codicon = ({ name }) => el('span', null, name)
export const PALETTE_AREA = 'palette'
export const ROUTES_AREA = 'routes'
export const SIDEBAR_NAV_AREA = 'sidebarNav'
export const pluginSettingsHref = id => `/settings?tab=plugins&plugin=${id}`
