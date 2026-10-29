<script setup lang="ts">
import { ref } from 'vue'
import { PhPlus, PhPencilSimple, PhTrash, PhFolderSimple, PhX } from '@phosphor-icons/vue'
import { api, destination } from '../api'
import type { Section } from '../api'
const props = defineProps<{ sections: Section[] }>()
const emit = defineEmits<{ changed: [] }>()
const editing = ref('')
const name = ref('')
const path = ref('')
const color = ref('blue')
const createFolder = ref(false)
const error = ref('')
const saving = ref(false)
const notice = ref('')
function edit(section: Section) {
  editing.value = section.id
  name.value = section.name
  path.value = section.path
  color.value = section.color
  createFolder.value = false
  error.value = ''
  notice.value = ''
}
function reset() {
  editing.value = ''
  name.value = ''
  path.value = ''
  color.value = 'blue'
  createFolder.value = false
}
async function save() {
  saving.value = true
  error.value = ''
  notice.value = ''
  try {
    await api(
      '/sections' + (editing.value ? '/' + editing.value : ''),
      editing.value ? 'PUT' : 'POST',
      { name: name.value, path: path.value, color: color.value, create_folder: createFolder.value },
    )
    notice.value = editing.value ? 'Section updated.' : 'Section added.'
    reset()
    emit('changed')
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Unable to save the section.'
  } finally {
    saving.value = false
  }
}
async function remove(section: Section) {
  error.value = ''
  saving.value = true
  try {
    await api('/sections/' + section.id, 'DELETE')
    if (editing.value === section.id) reset()
    emit('changed')
    notice.value = 'Shortcut removed. Your files remain on the drive.'
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Unable to remove the shortcut.'
  } finally {
    saving.value = false
  }
}
</script>
<template>
  <div class="settings-view">
    <h1>Settings</h1>
    <p class="muted mt-2 mb-7">Your sections, linked to folders on the drive.</p>
    <section class="panel p-6">
      <div class="flex justify-between items-center mb-5">
        <h2>{{ editing ? 'Edit section' : 'Add a section' }}</h2>
        <button v-if="editing" class="icon-button" aria-label="Cancel editing" @click="reset">
          <PhX :size="20" />
        </button>
      </div>
      <form novalidate class="space-y-5" @submit.prevent="save">
        <label class="field"
          >Section name<input v-model="name" required maxlength="80" placeholder="e.g. Books"
        /></label>
        <label class="field"
          >Folder on the drive<input
            v-model="path"
            maxlength="2048"
            placeholder="e.g. Books or Media/Books"
          /><span class="muted text-xs font-normal"
            >Path relative to the drive. Leave blank for the root.</span
          ></label
        >
        <label class="field"
          >Colour<select v-model="color">
            <option value="blue">Blue</option>
            <option value="purple">Purple</option>
            <option value="green">Green</option>
            <option value="yellow">Yellow</option>
            <option value="red">Red</option>
            <option value="slate">Grey</option>
          </select></label
        >
        <label class="flex gap-3 items-center text-sm muted"
          ><input v-model="createFolder" type="checkbox" />Create the folder if it does not
          exist</label
        >
        <p v-if="error" class="error-box" role="alert">{{ error }}</p>
        <p v-if="notice" class="color-green text-sm" role="status">{{ notice }}</p>
        <button class="primary" :disabled="saving">
          <PhPlus :size="18" />{{ saving ? 'Saving…' : editing ? 'Save changes' : 'Add section' }}
        </button>
      </form>
    </section>
    <div class="mt-7 mb-4 flex justify-between items-center">
      <h2>Sidebar sections</h2>
      <span class="muted text-sm">{{ props.sections.length }}</span>
    </div>
    <p v-if="!sections.length" class="panel p-6 muted">
      No sections yet. Add your first one above.
    </p>
    <ul v-else class="space-y-3">
      <li v-for="section in sections" :key="section.id" class="panel p-4 flex gap-3 items-center">
        <PhFolderSimple weight="fill" :size="32" :class="'color-' + section.color" />
        <div class="min-w-0 flex-1">
          <strong class="block truncate">{{ section.name }}</strong
          ><span class="block truncate muted text-sm" :title="destination(section.path)">{{
            destination(section.path)
          }}</span>
        </div>
        <button
          class="icon-button"
          :aria-label="'Edit ' + section.name"
          :disabled="saving"
          @click="edit(section)"
        >
          <PhPencilSimple :size="19" /></button
        ><button
          class="icon-button"
          :aria-label="'Remove shortcut ' + section.name"
          :disabled="saving"
          @click="remove(section)"
        >
          <PhTrash :size="19" />
        </button>
      </li>
    </ul>
    <p class="muted text-xs mt-5 leading-relaxed">
      Editing or removing a section only changes the shortcut. Your folders and files stay where
      they are.
    </p>
  </div>
</template>
