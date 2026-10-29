import { describe, expect, it } from 'vitest'
import { pathParts, selectionFromDrop, selectionFromEntries, selectionFromFiles } from './selection'

function pickedFile(name: string, relativePath: string) {
  const file = new File(['data'], name)
  Object.defineProperty(file, 'webkitRelativePath', { value: relativePath })
  return file
}

function fileEntry(name: string): FileSystemEntry {
  return {
    name,
    isFile: true,
    isDirectory: false,
    file: (success: (file: File) => void) => success(new File(['data'], name)),
  } as unknown as FileSystemEntry
}

function directoryEntry(name: string, children: FileSystemEntry[]): FileSystemEntry {
  return {
    name,
    isDirectory: true,
    isFile: false,
    createReader: () => {
      let offset = 0
      return {
        readEntries: (success: (entries: FileSystemEntry[]) => void) => {
          const batch = children.slice(offset, offset + 100)
          offset += batch.length
          success(batch)
        },
      }
    },
  } as unknown as FileSystemEntry
}

describe('folder selection', () => {
  it('preserves the selected root, nested paths and equal basenames in different subfolders', () => {
    const entries = selectionFromFiles([
      pickedFile('note.txt', 'Vacanze/Foto/note.txt'),
      pickedFile('note.txt', 'Vacanze/Documenti/note.txt'),
      pickedFile('altro.txt', 'Vacanze/Foto/altro.txt'),
    ])
    expect(entries.map((e) => [e.kind, e.relativePath])).toEqual([
      ['directory', 'Vacanze'],
      ['directory', 'Vacanze/Foto'],
      ['file', 'Vacanze/Foto/note.txt'],
      ['directory', 'Vacanze/Documenti'],
      ['file', 'Vacanze/Documenti/note.txt'],
      ['file', 'Vacanze/Foto/altro.txt'],
    ])
  })

  it('keeps ordinary selected files in the chosen destination without adding a folder', () => {
    expect(selectionFromFiles([new File(['a'], 'caffè.txt')]).map((e) => e.relativePath)).toEqual([
      'caffè.txt',
    ])
  })

  it('excludes Finder and AppleDouble files while retaining ordinary hidden files and similar names', () => {
    const names = [
      '.DS_Store',
      '.ds_store',
      '._photo.jpg',
      '._',
      'photo.jpg',
      '.gitignore',
      '.env',
      '.DS_Store.bak',
      'photo._small.jpg',
    ]
    expect(
      selectionFromFiles(names.map((name) => new File(['data'], name))).map((e) => e.relativePath),
    ).toEqual(['photo.jpg', '.gitignore', '.env', '.DS_Store.bak', 'photo._small.jpg'])
  })

  it('filters every selected path component before creating parent folder entries', () => {
    const entries = selectionFromFiles([
      pickedFile('.DS_Store', 'Album/.DS_Store'),
      pickedFile('._photo.jpg', 'Album/Metadata-only/._photo.jpg'),
      pickedFile('photo.jpg', 'Album/._Hidden/photo.jpg'),
      pickedFile('photo.jpg', 'Album/.DS_Store/photo.jpg'),
      pickedFile('photo.jpg', 'Album/Photos/photo.jpg'),
    ])
    expect(entries.map((e) => e.relativePath)).toEqual([
      'Album',
      'Album/Photos',
      'Album/Photos/photo.jpg',
    ])
  })

  it('returns an empty selection if a picked folder contains only excluded metadata', () => {
    expect(
      selectionFromFiles([
        pickedFile('.DS_Store', 'Album/.DS_Store'),
        pickedFile('._photo.jpg', 'Album/._photo.jpg'),
      ]),
    ).toEqual([])
  })

  it('skips dropped metadata before accessing files or descending into excluded folders', async () => {
    const excludedFile = {
      name: '._photo.jpg',
      isFile: true,
      file: () => {
        throw new Error('Metadata file must not be opened')
      },
    } as unknown as FileSystemEntry
    const excludedDirectory = {
      name: '._Photos',
      isDirectory: true,
      createReader: () => {
        throw new Error('Metadata folder must not be read')
      },
    } as unknown as FileSystemEntry
    const entries = await selectionFromEntries([
      directoryEntry('Album', [
        fileEntry('.DS_Store'),
        excludedFile,
        excludedDirectory,
        fileEntry('.gitignore'),
        fileEntry('photo.jpg'),
      ]),
    ])
    expect(entries.map((e) => e.relativePath)).toEqual([
      'Album',
      'Album/.gitignore',
      'Album/photo.jpg',
    ])
    expect(
      await selectionFromEntries([excludedFile, excludedDirectory, fileEntry('.DS_Store')]),
    ).toEqual([])
  })

  it('reads every batch beyond 100 children and includes empty dropped folders', async () => {
    const files = Array.from({ length: 205 }, (_, index) => fileEntry('file-' + index + '.txt'))
    const entries = await selectionFromEntries([
      directoryEntry('Raccolta', [directoryEntry('Vuota', []), ...files]),
    ])
    expect(entries).toHaveLength(207)
    expect(entries[1]).toEqual({ kind: 'directory', relativePath: 'Raccolta/Vuota' })
    expect(entries.at(-1)?.relativePath).toBe('Raccolta/file-204.txt')
  })

  it('captures all dropped roots while the browser drag data is still readable', async () => {
    let readable = true
    const data = {
      items: [
        {
          kind: 'file',
          webkitGetAsEntry: () => {
            expect(readable).toBe(true)
            return directoryEntry('Album', [fileEntry('uno.txt')])
          },
        },
      ],
    } as unknown as DataTransfer
    const promise = selectionFromDrop(data)
    readable = false
    expect((await promise).map((e) => e.relativePath)).toEqual(['Album', 'Album/uno.txt'])
  })

  it.each([
    '../escape.txt',
    '/absolute',
    'Album/../../escape',
    'Album/.minifiles/file',
    'a\\b',
    'a//b',
    'a/./b',
  ])('rejects unsafe paths: %s', (path) => {
    expect(() => pathParts(path)).toThrow('Invalid name or path')
  })
})
