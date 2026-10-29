<script setup lang="ts">
import { PhHardDrives, PhArrowsClockwise } from '@phosphor-icons/vue'
import { bytes } from '../api'
import type { Section, Stats } from '../api'
defineProps<{ stats: Stats | null; sections: Section[]; refreshing: boolean }>()
defineEmits<{ refresh: [] }>()
</script>
<template>
  <section class="panel storage-panel" aria-label="Drive statistics">
    <div class="panel-title">
      <PhHardDrives :size="24" />
      <h2>Disk usage</h2>
      <button
        class="icon-button ml-auto"
        :aria-disabled="refreshing"
        aria-label="Refresh statistics"
        @click="!refreshing && $emit('refresh')"
      >
        <PhArrowsClockwise :size="19" />
      </button>
    </div>
    <div v-if="stats" class="storage-content">
      <div class="flex justify-between gap-2 text-sm">
        <span
          ><strong class="text-base text-white">{{ bytes(stats.disk.used) }}</strong> /
          {{ bytes(stats.disk.total) }}</span
        ><span class="muted">{{ stats.disk.percent }}%</span>
      </div>
      <progress
        class="disk-progress"
        :value="stats.disk.percent"
        max="100"
        aria-label="Disk usage"
      />
      <p class="muted text-xs mt-2">{{ bytes(stats.disk.free) }} available</p>
      <ul class="section-stats">
        <li v-for="section in sections" :key="section.id">
          <span :class="['section-dot', 'bg-' + section.color]" /><span class="truncate flex-1">{{
            section.name
          }}</span
          ><span v-if="stats.sections[section.id]?.path === section.path" class="text-sm"
            >{{ stats.sections[section.id]?.partial ? '≥ ' : ''
            }}{{ bytes(stats.sections[section.id]?.bytes)
            }}<span
              v-if="stats.sections[section.id]?.partial"
              class="color-yellow"
              title="Partial scan: some paths are inaccessible"
            >
              *</span
            ></span
          ><span v-else class="muted text-sm" title="Refresh statistics to calculate">—</span>
        </li>
      </ul>
      <p v-if="!sections.length" class="muted text-sm mt-5">
        Add sections in Settings to measure your folders.
      </p>
      <p class="muted text-xs mt-5 leading-relaxed min-h-8">
        {{
          refreshing
            ? 'Updating statistics…'
            : stats.updated_at
              ? 'Folders updated ' + new Date(stats.updated_at * 1000).toLocaleString('en-GB')
              : 'Preparing folder statistics…'
        }}
      </p>
      <p
        v-if="sections.some((s) => stats?.sections[s.id]?.partial)"
        class="color-yellow text-xs mt-2"
      >
        * Partial result: check folders and permissions.
      </p>
    </div>
    <p v-else class="muted p-5 text-sm">Reading the filesystem…</p>
  </section>
</template>
