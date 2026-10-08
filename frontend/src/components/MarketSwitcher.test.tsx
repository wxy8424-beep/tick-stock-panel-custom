// @vitest-environment jsdom
import { act, useState } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { MarketSwitcher, type Market } from './MarketSwitcher'
import { PageHeader } from './PageHeader'

let host: HTMLDivElement
let root: Root
beforeEach(() => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true })
  host = document.createElement('div'); document.body.append(host)
  root = createRoot(host)
})
afterEach(async () => { await act(async () => root.unmount()); host.remove() })

it('defaults to enabled selected CN and clearly disabled pending HK/US', async () => {
  await act(async () => root.render(<MarketSwitcher />))
  const buttons = Array.from(host.querySelectorAll('button'))
  expect(buttons.map(button => button.textContent)).toEqual(['A股', '港股待开发', '美股待开发'])
  expect(buttons[0].disabled).toBe(false)
  expect(buttons[0].getAttribute('aria-pressed')).toBe('true')
  for (const button of buttons.slice(1)) {
    expect(button.disabled).toBe(true)
    expect(button.getAttribute('aria-pressed')).toBe('false')
    expect(button.title).toContain('待开发')
  }
})

it('unavailable clicks cannot change market or invoke the callback', async () => {
  const change = vi.fn()
  function Controlled() {
    const [market, setMarket] = useState<Market>('CN')
    return <MarketSwitcher value={market} onChange={next => { change(next); setMarket(next) }} />
  }
  await act(async () => root.render(<Controlled />))
  const buttons = host.querySelectorAll('button')
  await act(async () => { buttons[1].click(); buttons[2].click() })
  expect(change).not.toHaveBeenCalled()
  expect(buttons[0].getAttribute('aria-pressed')).toBe('true')
  await act(async () => buttons[0].click())
  expect(change).toHaveBeenCalledWith('CN')
})

it('opt-in header preserves the title, subtitle and original actions', async () => {
  const refresh = vi.fn()
  await act(async () => root.render(<PageHeader showMarketSwitcher title="自选股" subtitle="原 A 股内容" right={<button onClick={refresh}>刷新</button>} />))
  expect(host.querySelector('h1')?.textContent).toBe('自选股')
  expect(host.textContent).toContain('原 A 股内容')
  expect(host.querySelector('[aria-label="市场选择"]')).not.toBeNull()
  await act(async () => host.querySelector('header button')!.dispatchEvent(new MouseEvent('click', { bubbles: true })))
  expect(refresh).toHaveBeenCalledOnce()
})

it('ordinary headers such as Settings have no market controls', async () => {
  await act(async () => root.render(<PageHeader title="设置" />))
  expect(host.querySelector('[aria-label="市场选择"]')).toBeNull()
  expect(host.textContent).toBe('设置')
})
