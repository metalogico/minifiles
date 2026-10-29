import { describe, expect, it } from 'vitest'
import { createSSRApp } from 'vue'
import { renderToString } from 'vue/server-renderer'
import { summarizeQueue } from '../queue'
import type { QueueItem, QueueCounts, QueueActivity } from '../queue'
import UploadQueue from './UploadQueue.vue'
const counts = (): QueueCounts => ({ done: 0, skipped: 0, error: 0, cancelled: 0 })
function item(id: number, status: QueueItem['status']): QueueItem {
  return {
    id,
    batch: 1,
    kind: 'file',
    name: `file-${id}.zip`,
    size: 1024,
    file: null,
    path: 'ROMs',
    status,
    progress: 35,
    message: status === 'error' ? 'Disk full.' : 'Uploading',
  }
}
const render = (items: QueueItem[], archived = counts(), activity?: QueueActivity) =>
  renderToString(
    createSSRApp(UploadQueue, { items, summary: summarizeQueue(items, archived, activity) }),
  )
describe('fixed queue overview', () => {
  it('shows both progress bars only above the list and keeps archived progress after 1200 successes', async () => {
    const items = Array.from({ length: 374 }, (_, i) =>
      item(i + 1200, i === 0 ? 'uploading' : 'waiting'),
    )
    const html = await render(items, { ...counts(), done: 1200 })
    const overview = html.slice(0, html.indexOf('<ol'))
    const rows = html.slice(html.indexOf('<ol'))
    expect(overview).toContain('374 remaining')
    expect(overview).toContain('1,200 / 1,574 processed')
    expect(overview).toContain('file-1200.zip')
    expect(overview).toContain('35%')
    expect(overview).toContain('aria-label="Overall queue progress"')
    expect(overview).toContain('aria-label="Current file progress"')
    expect(rows).not.toContain('<progress')
    expect(html).not.toContain('Clear finished')
    expect(overview).toContain('Cancel queue')
  })
  it('shows skipped duplicates without overwrite controls', async () => {
    const html = await render([item(2, 'skipped'), item(3, 'waiting')], { ...counts(), done: 1 })
    const overview = html.slice(0, html.indexOf('<ol'))
    expect(overview).toContain('1 skipped')
    expect(html).not.toContain('Overwrite')
    expect(html).not.toContain('Waiting for your choice')
    expect(html.slice(html.indexOf('<ol'))).not.toContain('>Overwrite<')
  })
  it('always mounts the overview, both bar slots and the list when empty', async () => {
    const html = await render([])
    expect(html).toContain('Queue overview')
    expect(html).toContain('<ol')
    expect(html).toContain('No files queued')
    expect(html).toContain('Overall queue progress')
    expect(html).toContain('Current file progress')
  })
  it('shows graceful cancellation with the current file still visible', async () => {
    const current = item(1, 'uploading')
    const html = await render([current], counts(), {
      current,
      running: true,
      cancelling: true,
      cancelled: false,
      lastError: '',
    })
    expect(html).toContain('Finishing current file…')
    expect(html).toContain('file-1.zip')
    expect(html).toContain('disabled')
  })
  it('shows a final failure even after cancellation has emptied the rows', async () => {
    const html = await render([], counts(), {
      running: false,
      cancelling: false,
      cancelled: true,
      lastError: 'Disk full.',
    })
    expect(html).toContain('Queue cancelled')
    expect(html).toContain('Disk full.')
    expect(html).toContain('role="alert"')
    expect(html).not.toContain('All uploads completed')
  })
})
