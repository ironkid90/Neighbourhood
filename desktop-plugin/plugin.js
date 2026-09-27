/**
 * Neighbourhood — read-only ops board in Hermes Desktop.
 * Folder name must equal id. Reload via ⌘K → Reload desktop plugins.
 */
import {
  Badge,
  Button,
  EmptyState,
  ErrorState,
  GlyphSpinner,
  PALETTE_AREA,
  ROUTES_AREA,
  SIDEBAR_NAV_AREA,
  StatusDot,
  host,
  useQuery
} from '@hermes/plugin-sdk'
import { useEffect, useState } from 'react'
import { jsx, jsxs } from 'react/jsx-runtime'

const ID = 'neighbourhood'
const ROUTE = '/neighbourhood'
let lastSnapshot = null
let pluginContext = null

const CSS = `
.nhood{height:100%;overflow:auto;padding:18px 20px;color:var(--ui-text-primary)}
.nhood-bar{display:flex;flex-wrap:wrap;gap:10px 16px;align-items:baseline;margin-bottom:14px}
.nhood-kicker{font-size:11px;letter-spacing:.12em;text-transform:uppercase;color:var(--ui-text-quaternary)}
.nhood-title{font-size:20px;font-weight:650;margin-top:2px}
.nhood-pills{display:flex;flex-wrap:wrap;gap:6px;align-items:center}
.nhood-grid{display:grid;grid-template-columns:minmax(160px,22%) minmax(0,1fr) minmax(200px,30%);gap:12px}
.nhood h2{font-size:11px;letter-spacing:.1em;text-transform:uppercase;color:var(--ui-text-quaternary);margin:0 0 8px;font-weight:600}
.nhood-card{border:1px solid var(--ui-stroke-secondary);border-radius:8px;padding:9px 10px;margin-bottom:8px;background:transparent;color:inherit;width:100%;text-align:left;cursor:pointer}
.nhood-card:hover{background:var(--chrome-action-hover)}
.nhood-card[data-selected=true]{border-color:var(--ui-accent)}
.nhood-card[data-unread=true]{border-left:2px solid var(--ui-accent)}
.nhood-row{display:flex;gap:8px;align-items:center;justify-content:space-between}
.nhood-muted{color:var(--ui-text-tertiary);margin-top:3px;font-size:12px}
.nhood-tiny{color:var(--ui-text-quaternary);font-size:10px;margin-top:4px;overflow-wrap:anywhere}
.nhood-banner{border:1px solid var(--ui-danger,var(--ui-stroke-secondary));color:var(--ui-danger,var(--ui-text-secondary));border-radius:8px;padding:8px 10px;margin-bottom:12px;font-size:12px}
.nhood-work{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:8px;margin-top:14px;padding-top:12px;border-top:1px solid var(--ui-stroke-secondary)}
.nhood-dock{display:grid;grid-template-columns:1.4fr 0.8fr;gap:12px;margin-top:14px;padding-top:12px;border-top:1px solid var(--ui-stroke-secondary)}
.nhood-table{width:100%;border-collapse:collapse;font-size:12px}
.nhood-table th,.nhood-table td{text-align:left;padding:5px 6px;border-bottom:1px solid var(--ui-stroke-secondary);vertical-align:top}
.nhood-table th{color:var(--ui-text-quaternary);font-weight:550;font-size:10px;letter-spacing:.06em;text-transform:uppercase}
.nhood-center{display:flex;min-height:220px;align-items:center;justify-content:center}
@media(max-width:720px){.nhood-grid,.nhood-dock{grid-template-columns:1fr}}
`

async function loadSnapshot() {
  try {
    const live = await pluginContext.rest('/snapshot')
    if (live && live.built_at) {
      lastSnapshot = { ...live, source: 'rest' }
      return lastSnapshot
    }
  } catch {
    /* backend off until plugins.enabled — fall through to sibling JSON */
  }
  const url = new URL('./snapshot.json', import.meta.url)
  const res = await fetch(url)
  if (!res.ok) throw new Error('No neighbourhood snapshot (run dashboard/build.py)')
  const data = await res.json()
  const tagged = { ...data, source: 'file' }
  lastSnapshot = tagged
  return tagged
}

function htmlPathFromSnapshot(data) {
  const board = (data && data.board) || ''
  if (!board) return ''
  const slash = String.fromCharCode(92)
  const looksPosix = board.indexOf('/') >= 0 && board.indexOf(slash) < 0
  const sep = looksPosix ? '/' : slash
  let base = board
  while (base.endsWith('/') || base.endsWith(slash)) base = base.slice(0, -1)
  return base + sep + 'dashboard' + sep + 'index.html'
}

function openHtml() {
  const os = pluginContext && pluginContext.os
  const p = htmlPathFromSnapshot(lastSnapshot)
  if (!os || !p) return
  os.revealPath(p)
  os.openExternal('file:///' + p.split(String.fromCharCode(92)).join('/'))
}

function beadsLabel(data) {
  const beads = data?.beads
  if (!beads?.available) return 'bd n/a'
  const ip = (beads.in_progress || []).length
  const ready = (beads.ready || []).length
  const blocked = (beads.blocked || []).length
  return `bd ${ip}▶ ${ready}○ ${blocked}●`
}

function Chip() {
  const query = useQuery({
    queryKey: [ID, 'chip'],
    queryFn: loadSnapshot,
    refetchInterval: 20000,
    retry: false
  })
  const unread = query.data?.unread_handoffs || 0
  const fail = (query.data?.mcp_verified_fail || []).length
  const convoys = (query.data?.convoys || []).filter(c => !c.landed && c.status !== 'closed').length
  return jsx('button', {
    type: 'button',
    className: 'inline-flex h-full items-center gap-1 px-1.5 text-[0.6875rem] text-(--ui-text-tertiary) hover:bg-(--chrome-action-hover) hover:text-foreground',
    onClick: () => host.navigate(ROUTE),
    children: jsxs('span', {
      className: 'inline-flex items-center gap-1',
      children: [
        jsx(StatusDot, { tone: fail ? 'bad' : query.isError ? 'muted' : 'good' }),
        `Nhood${unread ? ` ${unread}` : ''}${convoys ? ` cv${convoys}` : ''}`
      ]
    })
  })
}

function issueCard(item) {
  const meta = []
  if (item.priority != null) meta.push(`P${item.priority}`)
  if (item.issue_type) meta.push(item.issue_type)
  if (item.assignee) meta.push(`@${item.assignee}`)
  return jsxs('article', {
    className: 'nhood-card',
    children: [
      jsxs('div', {
        className: 'nhood-row',
        children: [
          jsx('strong', { children: item.id }),
          jsx('span', { className: 'nhood-tiny', children: meta.join(' · ') })
        ]
      }),
      jsx('div', { className: 'nhood-muted', children: item.title || item.status || '' })
    ]
  }, item.id)
}

function Page() {
  const [selected, setSelected] = useState(null)
  const query = useQuery({
    queryKey: [ID, 'page'],
    queryFn: loadSnapshot,
    refetchInterval: 15000,
    retry: false
  })

  useEffect(() => {
    const style = document.createElement('style')
    style.dataset.nhood = 'true'
    style.textContent = CSS
    document.head.appendChild(style)
    return () => style.remove()
  }, [])

  if (query.isPending) {
    return jsx('div', { className: 'nhood-center', children: jsx(GlyphSpinner, {}) })
  }
  if (query.isError) {
    return jsx('div', {
      className: 'nhood',
      children: jsx(ErrorState, {
        title: 'Neighbourhood snapshot missing',
        description: query.error?.message || 'Run python ~/.neighbourhood/dashboard/build.py',
        action: jsxs('div', {
          className: 'flex gap-2',
          children: [
            jsx(Button, { onClick: () => query.refetch(), children: 'Retry' }),
            jsx(Button, { variant: 'ghost', onClick: openHtml, children: 'Open HTML' })
          ]
        })
      })
    })
  }

  const data = query.data
  const agents = data.agents || []
  const handoffs = data.handoffs || []
  const health = data.health?.primary || {}
  const servers = health.servers || []
  const work = data.workstreams || []
  const fail = data.mcp_verified_fail || []
  const convoys = data.convoys || []
  const trail = data.trail || []
  const formulas = data.formulas || []
  const beads = data.beads || {}
  const readyBeads = beads.ready || []
  const inProgress = beads.in_progress || []
  const staleAgents = data.stale_agents || []
  const pickedHandoff = handoffs.find(h => h.id === selected) || handoffs[0]
  const pickedConvoy = convoys.find(c => c.id === selected)
  const openCv = convoys.filter(c => !c.landed && c.status !== 'closed').length

  return jsxs('div', {
    className: 'nhood',
    children: [
      jsxs('header', {
        className: 'nhood-bar',
        children: [
          jsxs('div', {
            children: [
              jsx('div', { className: 'nhood-kicker', children: 'Neighbourhood' }),
              jsx('div', { className: 'nhood-title', children: 'Ops board' })
            ]
          }),
          jsxs('div', {
            className: 'nhood-pills',
            children: [
              jsx(Badge, { children: data.source === 'rest' ? 'live' : 'file snap' }),
              jsx(Badge, { children: fail.length ? `MCP FAIL ${fail.join(',')}` : 'MCP PASS' }),
              jsx(Badge, { children: beadsLabel(data) }),
              jsx(Badge, { children: data.gastown_lite ? `cv ${openCv} open` : 'cv n/a' }),
              jsx(Badge, { children: `${agents.length} agents` }),
              jsx(Badge, { children: `${data.unread_handoffs || 0} unread` }),
              jsx(Button, { size: 'sm', variant: 'ghost', onClick: () => query.refetch(), children: 'Refresh' }),
              jsx(Button, { size: 'sm', variant: 'ghost', onClick: openHtml, children: 'HTML' })
            ]
          })
        ]
      }),
      data.health?.stale_file
        ? jsx('div', { className: 'nhood-banner', children: 'health.json is stale vs health-latest.log. Trust the log until preflight rewrites it.' })
        : null,
      staleAgents.length
        ? jsx('div', {
            className: 'nhood-banner',
            children: `Witness-lite: stale heartbeat — ${staleAgents.map(a => a.agent).join(', ')} (45m).`
          })
        : null,
      jsxs('div', {
        className: 'nhood-grid',
        children: [
          jsxs('section', {
            children: [
              jsx('h2', { children: 'Agents' }),
              agents.length
                ? agents.map(agent => jsxs('article', {
                    className: 'nhood-card',
                    children: [
                      jsxs('div', {
                        className: 'nhood-row',
                        children: [
                          jsxs('span', {
                            className: 'inline-flex items-center gap-2',
                            children: [
                              jsx(StatusDot, { tone: agent.status === 'working' ? 'good' : 'muted' }),
                              jsx('strong', { children: agent.agent })
                            ]
                          }),
                          jsx('span', { className: 'nhood-tiny', children: agent.status })
                        ]
                      }),
                      jsx('div', { className: 'nhood-muted', children: agent.current_task || 'idle' }),
                      jsx('div', { className: 'nhood-tiny', children: agent.note || '' })
                    ]
                  }, agent.agent))
                : jsx(EmptyState, { title: 'No heartbeats' })
            ]
          }),
          jsxs('section', {
            children: [
              jsx('h2', { children: 'Convoys' }),
              convoys.length
                ? convoys.slice(0, 8).map(c => jsxs('button', {
                    className: 'nhood-card',
                    type: 'button',
                    'data-selected': selected === c.id,
                    onClick: () => setSelected(c.id),
                    children: [
                      jsxs('div', {
                        className: 'nhood-row',
                        children: [
                          jsx('strong', { children: c.id }),
                          jsx('span', { className: 'nhood-tiny', children: `${c.closed || 0}/${c.total || 0} ${c.landed ? 'landed' : c.status}` })
                        ]
                      }),
                      jsx('div', { className: 'nhood-muted', children: c.title }),
                      jsx('div', {
                        className: 'nhood-tiny',
                        children: (c.tracks || []).map(t => `${t.id} ${t.status}`).join(', ')
                      })
                    ]
                  }, c.id))
                : jsx(EmptyState, { title: 'No convoys' }),
              jsx('h2', { children: 'Handoffs' }),
              handoffs.length
                ? handoffs.slice(0, 12).map(h => jsxs('button', {
                    className: 'nhood-card',
                    type: 'button',
                    'data-unread': !h.read_by || h.read_by.length === 0,
                    'data-selected': pickedHandoff?.id === h.id && !pickedConvoy,
                    onClick: () => setSelected(h.id),
                    children: [
                      jsxs('div', {
                        className: 'nhood-row',
                        children: [
                          jsx('strong', { children: `${h.from_agent} → ${h.to_agent}` }),
                          jsx('span', { className: 'nhood-tiny', children: h.artifact_type })
                        ]
                      }),
                      jsx('div', { className: 'nhood-muted', children: h.summary }),
                      jsx('div', { className: 'nhood-tiny', children: h.timestamp })
                    ]
                  }, h.id))
                : jsx(EmptyState, { title: 'No handoffs' })
            ]
          }),
          jsxs('section', {
            children: [
              jsx('h2', { children: pickedConvoy ? 'Convoy' : pickedHandoff ? 'Inspector' : 'MCP probes' }),
              pickedConvoy
                ? jsxs('article', {
                    className: 'nhood-card',
                    children: [
                      jsx('strong', { children: pickedConvoy.title }),
                      jsx('div', { className: 'nhood-tiny', children: `${pickedConvoy.id} · ${pickedConvoy.closed}/${pickedConvoy.total}` }),
                      jsx('div', {
                        className: 'nhood-muted',
                        children: (pickedConvoy.tracks || []).map(t => `${t.id} [${t.status}] ${t.title || ''}`).join('\n')
                      })
                    ]
                  })
                : pickedHandoff
                  ? jsxs('article', {
                      className: 'nhood-card',
                      children: [
                        jsx('strong', { children: pickedHandoff.summary }),
                        jsx('div', { className: 'nhood-tiny', children: `${pickedHandoff.from_agent} → ${pickedHandoff.to_agent} · ${pickedHandoff.id}` }),
                        jsx('div', { className: 'nhood-muted', children: JSON.stringify(pickedHandoff.payload || {}, null, 2) })
                      ]
                    })
                  : null,
              jsx('h2', { children: beads.source || 'beads' }),
              inProgress.map(issueCard),
              readyBeads.map(issueCard),
              beads.available === false ? jsx(EmptyState, { title: beads.error || 'bd n/a' }) : null,
              jsx('h2', { children: health.source || 'probes' }),
              jsx('div', { className: 'nhood-tiny', children: health.checked_at || '' }),
              jsxs('table', {
                className: 'nhood-table',
                children: [
                  jsx('thead', {
                    children: jsxs('tr', {
                      children: [
                        jsx('th', { children: '' }),
                        jsx('th', { children: 'server' }),
                        jsx('th', { children: 'status' })
                      ]
                    })
                  }),
                  jsx('tbody', {
                    children: servers.map(s => jsxs('tr', {
                      children: [
                        jsx('td', { children: s.pass ? 'PASS' : 'FAIL' }),
                        jsx('td', { children: s.name }),
                        jsx('td', { children: s.status })
                      ]
                    }, s.name))
                  })
                ]
              })
            ]
          })
        ]
      }),
      jsxs('section', {
        className: 'nhood-dock',
        children: [
          jsxs('div', {
            children: [
              jsx('h2', { children: 'Trail' }),
              trail.length
                ? trail.slice(0, 16).map(t => jsxs('article', {
                    className: 'nhood-card',
                    children: [
                      jsxs('div', {
                        className: 'nhood-row',
                        children: [
                          jsx('strong', { children: t.kind }),
                          jsx('span', { className: 'nhood-tiny', children: t.at || '' })
                        ]
                      }),
                      jsx('div', { className: 'nhood-muted', children: t.title || t.id })
                    ]
                  }, `${t.kind}-${t.id}`))
                : jsx(EmptyState, { title: 'No trail' })
            ]
          }),
          jsxs('div', {
            children: [
              jsx('h2', { children: 'Formulas' }),
              formulas.length
                ? formulas.map(f => jsxs('article', {
                    className: 'nhood-card',
                    children: [
                      jsx('strong', { children: f.name }),
                      jsx('div', { className: 'nhood-tiny', children: (f.steps || []).join(' → ') }),
                      jsx('div', { className: 'nhood-muted', children: f.description || '' })
                    ]
                  }, f.name))
                : jsx(EmptyState, { title: 'No formulas' })
            ]
          })
        ]
      }),
      jsxs('section', {
        children: [
          jsx('h2', { children: 'Workstreams' }),
          jsx('div', {
            className: 'nhood-work',
            children: work.map(w => jsxs('article', {
              className: 'nhood-card',
              children: [
                jsx('div', { className: 'nhood-tiny', children: `${w.status} · ${w.owner}` }),
                jsx('strong', { children: w.title }),
                jsx('div', { className: 'nhood-muted', children: w.note })
              ]
            }, w.id))
          })
        ]
      })
    ]
  })
}

export default {
  id: ID,
  name: 'Neighbourhood',
  register(ctx) {
    pluginContext = ctx
    ctx.registerMany([
      { id: 'page', area: ROUTES_AREA, data: { path: ROUTE }, render: () => jsx(Page, {}) },
      { id: 'nav', area: SIDEBAR_NAV_AREA, data: { path: ROUTE, label: 'Neighbourhood', codicon: 'home' } },
      {
        id: 'open',
        area: PALETTE_AREA,
        data: {
          id: 'neighbourhood.open',
          label: 'Open Neighbourhood',
          keywords: ['neighbourhood', 'ops', 'mcp', 'handoff', 'convoy', 'beads', 'gastown'],
          run: () => host.navigate(ROUTE)
        }
      },
      { id: 'chip', area: 'statusBar.right', order: 140, render: () => jsx(Chip, {}) }
    ])
  }
}
