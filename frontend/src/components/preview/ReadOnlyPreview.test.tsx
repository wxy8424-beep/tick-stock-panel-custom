// @vitest-environment jsdom
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { PreviewNotice, PreviewDisabledAction, type PreviewDisabledActionProps } from './ReadOnlyPreview'

let host: HTMLDivElement, root: Root
beforeEach(() => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true })
  host = document.createElement('div'); document.body.append(host); root = createRoot(host)
})
afterEach(async () => { await act(async () => root.unmount()); host.remove(); vi.restoreAllMocks(); vi.unstubAllGlobals() })

it('notice retains accessible note/strong/paragraph DOM with caller-supplied wording and class', async () => {
  await act(async () => root.render(<PreviewNotice statement="合成只读样稿" description="不是生产数据" className="notice-custom" />))
  const note = host.querySelector('[role="note"]')!
  expect(note.tagName).toBe('DIV'); expect(note.className).toBe('notice-custom')
  expect(note.children).toHaveLength(2)
  expect(note.querySelector('strong')!.textContent).toBe('合成只读样稿')
  expect(note.querySelector('p')!.textContent).toBe('不是生产数据')
})
it('notice defaults match the existing Signal/Factor markup and escape text', async () => {
  await act(async () => root.render(<PreviewNotice statement="<script>sample</script>" description="<b>description</b>" />))
  expect(host.querySelector('script')).toBeNull(); expect(host.querySelector('b')).toBeNull()
  expect(host.querySelector('[role="note"]')!.className).toBe('rounded-xl border border-warning/30 bg-warning/5 p-4 text-sm text-warning')
  expect(host.textContent).toBe('<script>sample</script><b>description</b>')
})
it('action is a natively disabled non-submit button with original label suffix and accessible reason', async () => {
  await act(async () => root.render(<PreviewDisabledAction label="保存" reason="只读样稿不可保存" className="action-custom" />))
  const button = host.querySelector('button')!
  expect(button.type).toBe('button'); expect(button.disabled).toBe(true)
  expect(button.textContent).toBe('保存（Preview 不可执行）')
  expect(button.title).toBe('只读样稿不可保存'); expect(button.className).toBe('action-custom')
  expect(button.onclick).toBeNull()
})
it('action API excludes execution/enabled props and ignores unexpected runtime callbacks or overrides', async () => {
  const business = vi.fn()
  // @ts-expect-error An execution callback is intentionally not part of the public interface.
  const forbidden: PreviewDisabledActionProps = { label: '执行', reason: '只读', onClick: business }
  // Extra runtime properties must not be spread onto the native button.
  const injected = { ...forbidden, disabled: false, enabled: true, type: 'submit', onKeyDown: business }
  const element = PreviewDisabledAction(injected)
  expect(element.props.onClick).toBeUndefined(); expect(element.props.onKeyDown).toBeUndefined()
  expect(element.props.disabled).toBe(true); expect(element.props.type).toBe('button')
  await act(async () => root.render(<form onSubmit={business}><PreviewDisabledAction {...injected} /></form>))
  const button = host.querySelector('button')!
  await act(async () => {
    button.click()
    for (const key of ['Enter', ' ']) {
      button.dispatchEvent(new KeyboardEvent('keydown', { key, bubbles: true }))
      button.dispatchEvent(new KeyboardEvent('keyup', { key, bubbles: true }))
      button.click()
    }
  })
  expect(business).not.toHaveBeenCalled()
  // jsdom does not prove native browser keyboard activation or focus navigation.
})
it('both components mount, rerender and unmount without requests, storage access or notifications', async () => {
  const fetch = vi.fn(), notify = vi.fn(), stream = vi.fn()
  vi.stubGlobal('fetch', fetch); vi.stubGlobal('Notification', notify); vi.stubGlobal('EventSource', stream)
  const reads = vi.spyOn(Storage.prototype, 'getItem'), writes = vi.spyOn(Storage.prototype, 'setItem')
  const removes = vi.spyOn(Storage.prototype, 'removeItem'), clears = vi.spyOn(Storage.prototype, 'clear')
  for (const text of ['第一版', '第二版']) {
    await act(async () => root.render(<><PreviewNotice statement={text} description="固定样稿" /><PreviewDisabledAction label="执行" reason="Preview 不可执行" /></>))
    expect(host.querySelector('button')!.className).toBe('rounded-btn border border-border px-3 py-1 text-xs text-muted')
    await act(async () => host.querySelector('button')!.click())
  }
  await act(async () => root.render(null))
  for (const spy of [fetch, notify, stream, reads, writes, removes, clears]) expect(spy).not.toHaveBeenCalled()
})
