<script setup lang="ts">
import {
  PhUploadSimple,
  PhX,
  PhCheckCircle,
  PhWarningCircle,
  PhClock,
  PhSkipForward,
  PhHourglassSimple,
} from '@phosphor-icons/vue'
import { isSettled } from '../queue'
import type { QueueItem, QueueSummary } from '../queue'
import { bytes, destination } from '../api'
import FileIcon from './FileIcon.vue'
defineProps<{ items: QueueItem[]; summary: QueueSummary }>()
defineEmits<{ cancel: [item: QueueItem]; cancelAll: [] }>()
const number = (value: number) => new Intl.NumberFormat('en-GB').format(value)
</script>
<template>
  <section class="panel queue-panel" aria-label="Upload queue">
    <div class="panel-title">
      <PhUploadSimple class="color-blue" :size="23" />
      <h2>Upload queue</h2>
      <span class="count">{{ number(summary.total) }}</span
      ><button
        class="text-button queue-control ml-auto"
        :disabled="
          summary.state === 'cancelling' ||
          (!summary.total && !items.length && !summary.lastError && !summary.cancelledQueue)
        "
        @click="$emit('cancelAll')"
      >
        Cancel queue
      </button>
    </div>
    <div class="queue-summary" :data-state="summary.state" aria-label="Queue overview">
      <div class="queue-overview-line">
        <strong
          :class="
            summary.lastError || summary.error
              ? 'color-red'
              : summary.state === 'cancelling'
                ? 'color-yellow'
                : summary.state === 'running'
                  ? 'color-blue'
                  : summary.state === 'finished'
                    ? 'color-green'
                    : 'muted'
          "
          ><PhWarningCircle
            v-if="summary.lastError || summary.error"
            :size="17"
          /><PhHourglassSimple
            v-else-if="summary.state === 'cancelling'"
            :size="17"
          /><PhUploadSimple v-else-if="summary.state === 'running'" :size="17" /><PhCheckCircle
            v-else
            :size="17"
          />{{ summary.label }}</strong
        ><span class="muted tabular-nums">{{ number(summary.remaining) }} remaining</span>
      </div>
      <progress
        :class="{ invisible: !summary.total }"
        :value="summary.processed"
        :max="Math.max(1, summary.total)"
        aria-label="Overall queue progress"
      />
      <div
        class="queue-outcomes muted"
        :title="summary.processed + ' / ' + summary.total + ' processed'"
      >
        <span class="tabular-nums"
          >{{ number(summary.processed) }} / {{ number(summary.total) }} processed</span
        ><span v-if="summary.error" class="color-red">{{ number(summary.error) }} failed</span
        ><span v-if="summary.skipped">{{ number(summary.skipped) }} skipped</span
        ><span v-if="summary.cancelled">{{ number(summary.cancelled) }} cancelled</span>
      </div>
      <div
        class="queue-current filename"
        :title="
          summary.current
            ? destination(summary.current.path) + ' / ' + summary.current.name
            : undefined
        "
      >
        {{ summary.current?.name || 'No uploads running' }}
      </div>
      <div
        :class="['queue-current-note', { 'color-red': summary.lastError }]"
        :role="summary.lastError ? 'alert' : undefined"
        :title="summary.lastError || summary.current?.message"
      >
        {{ summary.lastError || summary.current?.message || ' ' }}
      </div>
      <div class="queue-current-action">
        <div
          :class="['queue-current-progress', { invisible: summary.current?.kind !== 'file' }]"
          :aria-hidden="summary.current?.kind !== 'file'"
        >
          <progress
            :value="summary.current?.progress || 0"
            max="100"
            aria-label="Current file progress"
          /><span class="muted tabular-nums">{{ summary.current?.progress || 0 }}%</span>
        </div>
      </div>
    </div>
    <ol class="queue-items" aria-label="Queued items">
      <li v-if="!items.length" class="queue-empty">
        <PhUploadSimple :size="32" />
        <p>No files queued</p>
        <span>Successful uploads are removed automatically.</span>
      </li>
      <li v-for="item in items" :key="item.id" class="queue-item">
        <FileIcon :name="item.name" :kind="item.kind" />
        <div class="min-w-0 flex-1">
          <div class="flex items-start gap-2">
            <strong class="filename flex-1" :title="item.name">{{ item.name }}</strong
            ><button
              v-if="!isSettled(item)"
              class="icon-button small queue-control"
              :disabled="summary.state === 'cancelling'"
              :aria-label="'Cancel ' + item.name"
              @click="$emit('cancel', item)"
            >
              <PhX :size="17" /></button
            ><PhWarningCircle
              v-else-if="item.status === 'error'"
              class="color-red shrink-0"
              :size="22"
            /><PhSkipForward v-else-if="item.status === 'skipped'" :size="20" /><PhX
              v-else
              :size="20"
            />
          </div>
          <div class="muted text-sm mt-1">
            {{ item.kind === 'directory' ? 'Folder' : bytes(item.size) }}
          </div>
          <div class="queue-destination" :title="destination(item.path)">
            {{ destination(item.path) }}
          </div>
          <div
            :class="['queue-status', { 'color-red': item.status === 'error' }]"
            :role="item.status === 'error' ? 'alert' : undefined"
          >
            <PhClock v-if="item.status === 'waiting'" :size="13" />{{ item.message }}
          </div>
        </div>
      </li>
    </ol>
  </section>
</template>
