<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import {
  PhFolderSimple,
  PhHouse,
  PhGearSix,
  PhSignOut,
  PhCloudArrowUp,
  PhSquaresFour,
  PhList,
  PhCaretRight,
  PhArrowClockwise,
  PhArrowLeft,
  PhMagnifyingGlass,
  PhLockKey,
  PhHourglassSimple,
} from '@phosphor-icons/vue'
import { api, ApiError, bytes, destination } from './api'
import type { Entry, Section } from './api'
import { createQueue } from './queue'
import { createStatsController } from './stats'
import { selectionFromDrop, selectionFromFiles } from './selection'
import FileIcon from './components/FileIcon.vue'
import UploadQueue from './components/UploadQueue.vue'
import StoragePanel from './components/StoragePanel.vue'
import SettingsView from './components/SettingsView.vue'

const ready = ref(false)
const username = ref('')
const loginName = ref('')
const password = ref('')
const loginError = ref('')
const loggingIn = ref(false)
const sections = ref<Section[]>([])
const entries = ref<Entry[]>([])
const path = ref('')
const view = ref<'files' | 'settings'>('files')
const mode = ref('grid')
const search = ref('')
const error = ref('')
const loading = ref(false)
const dragging = ref(false)
const input = ref<HTMLInputElement>()
const folderInput = ref<HTMLInputElement>()
const preparing = ref(false)

const queue = createQueue({
  completed: () => {
    if (view.value === 'files') void loadFiles()
  },
  drained: () => {
    void statistics.queueFinished()
  },
  expired: expire,
})
const statistics = createStatsController(() => queue.summary.busy, showError)
const { stats, updating: statsUpdating } = statistics
let folderRequest = 0
let selectionGeneration = 0
const active = computed(() => queue.summary.busy)
const activityLabel = computed(() => {
  if (preparing.value) return 'Reading selected folders'
  if (active.value) return 'Upload queue active'
  if (loading.value) return 'Refreshing folder'
  return ''
})
const activeSection = computed(
  () =>
    sections.value
      .filter((s) => s.path && (path.value === s.path || path.value.startsWith(s.path + '/')))
      .sort((a, b) => b.path.length - a.path.length)[0]?.id,
)
const visible = computed(() =>
  entries.value.filter((e) =>
    e.name.toLocaleLowerCase().includes(search.value.toLocaleLowerCase()),
  ),
)
const breadcrumbs = computed(() =>
  path.value
    .split('/')
    .filter(Boolean)
    .map((name, i, all) => ({ name, path: all.slice(0, i + 1).join('/') })),
)
function expire() {
  selectionGeneration++
  preparing.value = false
  queue.reset()
  statistics.reset()
  username.value = ''
  password.value = ''
  loginError.value = 'Your session has expired. Sign in again.'
}
function showError(e: unknown) {
  if (e instanceof ApiError && e.status === 401) expire()
  else error.value = e instanceof Error ? e.message : 'Unable to connect to the server.'
}
async function loadSections() {
  try {
    sections.value = await api('/sections')
  } catch (e) {
    showError(e)
  }
}
async function loadFiles() {
  const id = ++folderRequest
  loading.value = true
  error.value = ''
  try {
    const result = await api<{ entries: Entry[] }>('/files?path=' + encodeURIComponent(path.value))
    if (id === folderRequest) entries.value = result.entries
  } catch (e) {
    if (id === folderRequest) showError(e)
  } finally {
    if (id === folderRequest) loading.value = false
  }
}
function navigate(target: string) {
  if (target !== path.value) entries.value = []
  view.value = 'files'
  path.value = target
  search.value = ''
  void loadFiles()
}
function openSettings() {
  view.value = 'settings'
  error.value = ''
}
async function boot() {
  void statistics.load()
  await Promise.all([loadSections(), loadFiles()])
}
async function login() {
  if (!loginName.value.trim() || !password.value) {
    loginError.value = 'Enter your username and password.'
    return
  }
  loginError.value = ''
  loggingIn.value = true
  try {
    const session = await api('/login', 'POST', {
      username: loginName.value,
      password: password.value,
    })
    username.value = session.username
    password.value = ''
    await boot()
  } catch (e) {
    loginError.value = e instanceof Error ? e.message : 'Unable to connect to the server.'
  } finally {
    loggingIn.value = false
  }
}
async function logout() {
  selectionGeneration++
  preparing.value = false
  queue.reset()
  statistics.reset()
  try {
    await api('/logout', 'POST')
    username.value = ''
    path.value = ''
    view.value = 'files'
    stats.value = null
    entries.value = []
    sections.value = []
  } catch (e) {
    showError(e)
  }
}
function addFiles(files: File[]) {
  if (queue.accepting && files.length) {
    try {
      queue.add(selectionFromFiles(files), path.value)
    } catch (e) {
      showError(e)
    }
  }
}
function selected(event: Event) {
  const element = event.target as HTMLInputElement
  if (!queue.accepting) {
    element.value = ''
    return
  }
  const files = Array.from(element.files || [])
  if (element.webkitdirectory && !files.length)
    error.value = 'The selected folder contains no files. Drop it here to include empty folders.'
  else addFiles(files)
  element.value = ''
}
async function drop(event: DragEvent) {
  dragging.value = false
  if (!event.dataTransfer || preparing.value || !queue.accepting) return
  const target = path.value
  const generation = selectionGeneration
  preparing.value = true
  error.value = ''
  try {
    const entries = await selectionFromDrop(event.dataTransfer)
    if (generation === selectionGeneration && username.value && queue.accepting && entries.length)
      queue.add(entries, target)
  } catch (e) {
    if (generation === selectionGeneration) showError(e)
  } finally {
    if (generation === selectionGeneration) preparing.value = false
  }
}
function paste(event: ClipboardEvent) {
  if (
    username.value &&
    view.value === 'files' &&
    !['INPUT', 'TEXTAREA'].includes((event.target as HTMLElement)?.tagName)
  )
    addFiles(Array.from(event.clipboardData?.files || []))
}
function refreshStats() {
  void statistics.refresh()
}
async function settingsChanged() {
  await loadSections()
}
function cancelQueue() {
  selectionGeneration++
  preparing.value = false
  queue.cancelAll()
}
function pagehide() {
  selectionGeneration++
  queue.reset()
  statistics.reset()
}
onMounted(async () => {
  try {
    username.value = (await api('/session')).username
    await boot()
  } catch (e) {
    if (!(e instanceof ApiError && e.status === 401)) showError(e)
  }
  ready.value = true
  window.addEventListener('paste', paste)
  window.addEventListener('pagehide', pagehide)
})
onUnmounted(() => {
  queue.reset()
  statistics.reset()
  window.removeEventListener('paste', paste)
  window.removeEventListener('pagehide', pagehide)
})
</script>

<template>
  <div v-if="!ready" class="login-screen muted">Opening MiniFiles…</div>
  <main v-else-if="!username" class="login-screen">
    <div class="login-card panel">
      <div class="brand justify-center">
        <PhFolderSimple weight="fill" :size="43" class="color-blue" /><span><b>Mini</b>Files</span>
      </div>
      <h1 class="text-center mt-8">Your space, at home.</h1>
      <p class="muted text-center text-sm mt-2 mb-8">
        Sign in to browse your drive and upload files.
      </p>
      <form novalidate class="space-y-5" @submit.prevent="login">
        <label class="field"
          >Username<input v-model="loginName" autocomplete="username" required autofocus /></label
        ><label class="field"
          >Password<input
            v-model="password"
            autocomplete="current-password"
            type="password"
            required
        /></label>
        <p v-if="loginError || error" class="error-box" role="alert">{{ loginError || error }}</p>
        <button class="primary w-full justify-center" :disabled="loggingIn">
          <PhLockKey :size="19" />{{ loggingIn ? 'Signing in…' : 'Sign in' }}
        </button>
      </form>
    </div>
  </main>
  <div v-else class="app-shell">
    <aside class="sidebar">
      <a href="#" class="brand" aria-label="MiniFiles, drive root" @click.prevent="navigate('')"
        ><PhFolderSimple weight="fill" :size="43" class="color-blue" /><span
          ><b>Mini</b>Files</span
        ></a
      >
      <nav class="navigation" aria-label="Drive navigation">
        <button
          :class="['nav-item', { selected: view === 'files' && path === '' }]"
          @click="navigate('')"
        >
          <PhHouse :size="27" :weight="path === '' ? 'fill' : 'regular'" /><span
            >Drive</span
          ></button
        ><button
          v-for="section in sections"
          :key="section.id"
          :class="['nav-item', { selected: view === 'files' && activeSection === section.id }]"
          :title="destination(section.path)"
          @click="navigate(section.path)"
        >
          <PhFolderSimple :size="27" :class="'color-' + section.color" /><span class="truncate">{{
            section.name
          }}</span>
        </button>
        <p v-if="!sections.length" class="muted text-xs px-4 mt-3 leading-relaxed">
          Your favourite folders?<br />Add them in Settings.
        </p>
      </nav>
      <div class="sidebar-bottom">
        <button
          :class="['nav-item', { selected: view === 'settings' }]"
          aria-label="Settings"
          @click="openSettings"
        >
          <PhGearSix :size="25" /><span>Settings</span></button
        ><button class="nav-item" aria-label="Sign out" @click="logout">
          <PhSignOut :size="24" /><span>Sign out</span
          ><span class="text-xs muted truncate ml-auto">{{ username }}</span>
        </button>
      </div>
    </aside>
    <main class="workspace">
      <header class="workspace-header">
        <div class="breadcrumbs" aria-label="Location">
          <button class="icon-button" aria-label="Drive root" @click="navigate('')">
            <PhHouse weight="fill" :size="24" /></button
          ><PhCaretRight :size="15" /><button @click="navigate('')">Drive</button
          ><template v-if="view === 'files'" v-for="crumb in breadcrumbs" :key="crumb.path"
            ><PhCaretRight :size="15" /><button
              :class="{ 'text-white font-semibold': crumb.path === path }"
              @click="navigate(crumb.path)"
            >
              {{ crumb.name }}
            </button></template
          ><template v-if="view === 'settings'"
            ><PhCaretRight :size="15" /><span class="text-white">Settings</span></template
          >
        </div>
        <div v-if="view === 'files'" class="view-switch">
          <button
            :class="{ active: mode === 'grid' }"
            aria-label="Grid view"
            :aria-pressed="mode === 'grid'"
            @click="mode = 'grid'"
          >
            <PhSquaresFour weight="fill" :size="22" /></button
          ><button
            :class="{ active: mode === 'list' }"
            aria-label="List view"
            :aria-pressed="mode === 'list'"
            @click="mode = 'list'"
          >
            <PhList :size="22" />
          </button>
        </div>
      </header>
      <p v-if="error" class="error-box mb-5" role="alert">{{ error }}</p>
      <SettingsView v-if="view === 'settings'" :sections="sections" @changed="settingsChanged" />
      <div v-else>
        <section
          :class="['upload-zone', { dragging }]"
          @dragover.prevent="dragging = true"
          @dragleave.prevent="dragging = false"
          @drop.prevent="drop"
        >
          <PhCloudArrowUp weight="fill" :size="67" class="color-blue" />
          <h1>Drop files and folders here</h1>
          <p class="muted destination-line">
            Destination: <strong>{{ destination(path) }}</strong>
          </p>
          <div class="flex items-center justify-center gap-3 my-4">
            <button
              class="primary browse-button"
              :disabled="preparing || !queue.accepting"
              @click="input?.click()"
            >
              <PhFolderSimple :size="25" weight="fill" />Choose files</button
            ><button
              class="secondary browse-button"
              :disabled="preparing || !queue.accepting"
              @click="folderInput?.click()"
            >
              <PhFolderSimple :size="25" />Choose folder
            </button>
          </div>
          <p class="muted text-sm">Keeps subfolders and each file’s destination.</p>
          <input
            ref="input"
            type="file"
            multiple
            class="sr-only"
            tabindex="-1"
            aria-label="Select files to upload"
            @change="selected"
          /><input
            ref="folderInput"
            type="file"
            webkitdirectory
            multiple
            class="sr-only"
            tabindex="-1"
            aria-label="Select a folder to upload"
            @change="selected"
          />
        </section>
        <div class="file-toolbar">
          <div class="flex items-center gap-2 min-w-0">
            <button
              v-if="path"
              class="icon-button"
              aria-label="Parent folder"
              @click="navigate(path.split('/').slice(0, -1).join('/'))"
            >
              <PhArrowLeft :size="19" /></button
            ><span class="muted text-sm tabular-nums min-w-20"
              >{{ visible.length }} {{ visible.length === 1 ? 'item' : 'items' }}</span
            ><button
              class="icon-button"
              aria-label="Refresh folder"
              :aria-disabled="loading"
              @click="!loading && loadFiles()"
            >
              <PhArrowClockwise :size="18" />
            </button>
          </div>
          <div class="flex items-center gap-3 min-w-0">
            <span
              class="folder-activity"
              role="status"
              :aria-label="activityLabel || undefined"
              :title="activityLabel || undefined"
              ><PhHourglassSimple
                :size="19"
                :class="{ invisible: !activityLabel }"
                aria-hidden="true"
            /></span>
            <label class="search-field"
              ><PhMagnifyingGlass :size="18" /><input
                v-model="search"
                aria-label="Search this folder"
                placeholder="Search this folder"
            /></label>
          </div>
        </div>
        <div
          v-if="!visible.length"
          :class="['empty-folder panel', { invisible: loading && !entries.length }]"
          :aria-busy="loading"
        >
          <PhFolderSimple :size="60" class="color-blue" weight="duotone" />
          <h2>{{ search ? 'No results' : 'This folder is empty' }}</h2>
          <p class="muted text-sm">
            {{ search ? 'Try another name.' : 'Choose files above to get started.' }}
          </p>
        </div>
        <div
          v-else
          :class="['file-grid', { 'file-list': mode === 'list' }]"
          aria-label="Folder contents"
          :aria-busy="loading"
        >
          <component
            :is="entry.kind === 'directory' ? 'button' : 'div'"
            v-for="(entry, index) in visible"
            :key="entry.name"
            :class="[
              'file-card panel',
              {
                'folder-card': entry.kind === 'directory',
                'blocked-card': entry.kind === 'blocked',
              },
            ]"
            :aria-label="entry.kind === 'directory' ? 'Open folder ' + entry.name : undefined"
            @click="
              entry.kind === 'directory' && navigate([path, entry.name].filter(Boolean).join('/'))
            "
            ><FileIcon :name="entry.name" :kind="entry.kind" :index="index" /><strong
              class="filename"
              :title="entry.name"
              >{{ entry.name }}</strong
            ><span class="muted text-sm">{{
              entry.kind === 'directory'
                ? 'Folder'
                : entry.kind === 'blocked'
                  ? 'Unavailable link'
                  : bytes(entry.size)
            }}</span
            ><time
              class="file-date muted text-xs"
              :datetime="new Date(entry.modified * 1000).toISOString()"
              >{{ new Date(entry.modified * 1000).toLocaleDateString('en-GB') }}</time
            ></component
          >
        </div>
      </div>
    </main>
    <aside class="right-column">
      <UploadQueue
        :items="queue.items"
        :summary="queue.summary"
        @cancel="queue.cancel"
        @cancel-all="cancelQueue"
      /><StoragePanel
        :stats="stats"
        :sections="sections"
        :refreshing="statsUpdating"
        @refresh="refreshStats"
      />
      <p v-if="active" class="muted text-xs leading-relaxed px-2">
        You can browse and open Settings while uploads continue. Keep this page open until all
        uploads finish.
      </p>
    </aside>
  </div>
</template>
