export type UploadEntry =
  { kind: 'file'; relativePath: string; file: File } | { kind: 'directory'; relativePath: string }

export const isMacMetadata = (name: string) =>
  name.toLowerCase() === '.ds_store' || name.startsWith('._')

export function pathParts(path: string): string[] {
  const parts = path.split('/')
  if (
    !path ||
    path.length > 2048 ||
    parts.some(
      (part) =>
        !part ||
        ['.', '..', '.minifiles'].includes(part) ||
        /[\\\u0000-\u001f\u007f]/.test(part) ||
        new TextEncoder().encode(part).length > 255,
    )
  ) {
    throw new Error(`Invalid name or path: ${path}`)
  }
  return parts
}

export function selectionFromFiles(files: Iterable<File>): UploadEntry[] {
  const entries: UploadEntry[] = []
  const directories = new Set<string>()
  for (const file of files) {
    const relativePath = file.webkitRelativePath || file.name
    const parts = pathParts(relativePath)
    if (parts.some(isMacMetadata)) continue
    for (let depth = 1; depth < parts.length; depth++) {
      const path = parts.slice(0, depth).join('/')
      if (!directories.has(path)) {
        directories.add(path)
        entries.push({ kind: 'directory', relativePath: path })
      }
    }
    entries.push({ kind: 'file', relativePath, file })
  }
  return entries
}

export async function selectionFromEntries(roots: FileSystemEntry[]): Promise<UploadEntry[]> {
  const result: UploadEntry[] = []
  async function visit(entry: FileSystemEntry, parent: string) {
    if (isMacMetadata(entry.name)) return
    const relativePath = parent ? parent + '/' + entry.name : entry.name
    pathParts(relativePath)
    if (entry.isFile) {
      const file = await new Promise<File>((resolve, reject) =>
        (entry as FileSystemFileEntry).file(resolve, reject),
      )
      result.push({ kind: 'file', relativePath, file })
    } else if (entry.isDirectory) {
      result.push({ kind: 'directory', relativePath })
      const reader = (entry as FileSystemDirectoryEntry).createReader()
      // Chromium returns at most 100 children per call. Read until the empty batch.
      while (true) {
        const batch = await new Promise<FileSystemEntry[]>((resolve, reject) =>
          reader.readEntries(resolve, reject),
        )
        if (!batch.length) break
        for (const child of batch) await visit(child, relativePath)
      }
    }
  }
  for (const root of roots) await visit(root, '')
  return result
}

export function selectionFromDrop(data: DataTransfer): Promise<UploadEntry[]> {
  // Capture entries synchronously while the drop event still grants access.
  const roots: FileSystemEntry[] = []
  for (const item of Array.from(data.items)) {
    if (item.kind !== 'file') continue
    const entry = item.webkitGetAsEntry()
    if (!entry)
      throw new Error('Unable to read the dropped items. Use Choose files or Choose folder.')
    roots.push(entry)
  }
  return selectionFromEntries(roots)
}
