// Where does a request from a button go? Runs the plugin's own ask() against the stub SDK, which
// keeps the app's contract: submit refuses when no chat is on screen.
import { host, state } from '@hermes/plugin-sdk'
import { __test } from './plugin.js'

const out = {}
async function run(name, setup) {
  Object.assign(state, { sent: [], chat: true, newChatAfter: 2, opened: false, tries: 0 })
  setup()
  await __test.ask('Expand Pioneer gap r1.g3 into a new round.')
  out[name] = state.sent
}
await run('chatOnScreen', () => {})
await run('pageNoChat', () => { state.chat = false })
await run('newChatNeverMounts', () => { state.chat = false; state.newChatAfter = -1 })
const newChat = host.newChat
delete host.newChat
await run('olderAppNoNewChat', () => { state.chat = false })
host.newChat = newChat
// two fast clicks send once
Object.assign(state, { sent: [], chat: false, newChatAfter: 2, opened: false, tries: 0 })
await Promise.all([__test.ask('Run the Pioneer absence check on gap r1.g1.'), __test.ask('Run the Pioneer absence check on gap r1.g1.')])
out.doubleClick = state.sent
out.aims = [
  'Hermes Agent plugins',
  '  a solo founder   running client agents?  ',
  'Run pioneer on this workspace. What should exist for Hermes Agent plugins?',
  'Run pioneer on this workspace. What should exist for Run pioneer on this workspace. What should exist for Hermes Agent plugins?',
  'what should exist for guest houses.',
  '   ', '?'
].map(__test.cleanAim)
process.stdout.write(JSON.stringify(out))
