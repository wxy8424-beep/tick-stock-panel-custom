// @vitest-environment jsdom
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import type { ColumnConfig } from '@/lib/list-columns'
import { StockDataTable, type StockDataTableProps } from './StockDataTable'
import { useTableSort } from './useTableSort'

const columns: ColumnConfig[] = [
  { id: 'price', label: '参考价', visible: true, align: 'right', source: { type: 'builtin', key: 'price' } },
  { id: 'candle', label: '日k', visible: true, align: 'center', source: { type: 'builtin', key: 'candle' } },
]
const rows = [{ symbol: '600000.SH', price: 3 }, { symbol: '000001.SZ', price: 1 }, { symbol: '600001.SH', price: null }]
let host: HTMLDivElement, root: Root
beforeEach(() => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true })
  host = document.createElement('div'); document.body.append(host); root = createRoot(host)
})
afterEach(async () => { await act(async () => root.unmount()); host.remove() })
const renderCell = (row: typeof rows[number], col: ColumnConfig) => <td>{col.id === 'price' ? row.price ?? '—' : row.symbol}</td>
async function render(props: Partial<StockDataTableProps> = {}) {
  const calls = vi.fn()
  function Harness() {
    const { sort, toggle, sortRows } = useTableSort<typeof rows[number]>((row) => row.price)
    return <StockDataTable columns={columns} rows={sortRows(rows, columns)} renderCell={renderCell}
      sort={sort} onSortToggle={key => { calls(key); toggle(key) }} {...props} />
  }
  await act(async () => root.render(<Harness />))
  return calls
}
const header = () => host.querySelector('th')!
const sortButton = () => header().querySelector('button')!
const prices = () => [...host.querySelectorAll('tbody tr')].map(tr => tr.firstElementChild?.textContent)

it('native sortable buttons expose column scope, focus and controlled aria-sort', async () => {
  await render()
  expect(header().getAttribute('scope')).toBe('col')
  expect(header().getAttribute('aria-sort')).toBe('none')
  expect(sortButton().type).toBe('button'); expect(sortButton().tabIndex).toBe(0)
  expect(sortButton().getAttribute('aria-label')).toBe('按参考价排序')
  sortButton().focus(); expect(document.activeElement).toBe(sortButton())
  expect(sortButton().querySelector('[aria-hidden="true"]')).not.toBeNull()
})
it('native keyboard activation click cycles once without duplicate key handlers or bubbling', async () => {
  const calls = await render()
  // jsdom does not synthesize native keyboard clicks. Dispatch the browser activation click
  // after the key sequence; real Edge separately verifies Tab/Enter/Space defaults.
  for (const [key, expected, values] of [
    ['Enter', 'ascending', ['1', '3', '—']], [' ', 'descending', ['3', '1', '—']], ['Enter', 'none', ['3', '1', '—']],
  ] as const) {
    const before = calls.mock.calls.length
    await act(async () => {
      sortButton().dispatchEvent(new KeyboardEvent('keydown', { key, bubbles: true }))
      sortButton().dispatchEvent(new KeyboardEvent('keyup', { key, bubbles: true }))
      expect(calls).toHaveBeenCalledTimes(before)
      sortButton().click()
    })
    expect(calls).toHaveBeenCalledTimes(before + 1)
    expect(header().getAttribute('aria-sort')).toBe(expected); expect(prices()).toEqual(values)
  }
})
it('legacy header and mouse button clicks retain CN tri-state sorting and null-last rows', async () => {
  const calls = await render()
  await act(async () => header().click()); expect(prices()).toEqual(['1', '3', '—'])
  await act(async () => sortButton().click()); expect(prices()).toEqual(['3', '1', '—'])
  expect(calls).toHaveBeenCalledTimes(2)
  await act(async () => header().click()); expect(header().getAttribute('aria-sort')).toBe('none')
  expect(rows.map(row => row.price)).toEqual([3, 1, null])
})
it('unsortable builtin columns and read-only tables gain no sorting actions', async () => {
  await render()
  expect(host.querySelectorAll('th')[1].querySelector('button')).toBeNull()
  expect(host.querySelectorAll('th')[1].hasAttribute('aria-sort')).toBe(false)
  await render({ onSortToggle: undefined })
  expect(host.querySelector('thead button')).toBeNull()
  expect(header().hasAttribute('aria-sort')).toBe(false)
})
it('custom CN header controls remain independent without nested buttons', async () => {
  const eye = vi.fn()
  const calls = await render({ extraSortableKeys: new Set(['candle']), renderHeaderContent: col => col.id === 'candle'
    ? <button type="button" aria-label="显示日k" onClick={e => { e.stopPropagation(); eye() }}>日k</button> : undefined })
  expect(host.querySelector('button button')).toBeNull()
  await act(async () => host.querySelector<HTMLButtonElement>('[aria-label="显示日k"]')!.click())
  expect(eye).toHaveBeenCalledTimes(1); expect(calls).not.toHaveBeenCalled()
  await act(async () => host.querySelector<HTMLButtonElement>('[aria-label="按日k排序"]')!.click())
  expect(calls).toHaveBeenCalledExactlyOnceWith('candle')
  expect(host.querySelectorAll('th')[1].getAttribute('aria-sort')).toBe('ascending')
  expect(header().getAttribute('aria-sort')).toBe('none')
})
