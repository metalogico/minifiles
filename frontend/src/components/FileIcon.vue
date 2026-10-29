<script setup lang="ts">
import { computed } from 'vue'
import {
  PhFolderSimple,
  PhFile,
  PhFilePdf,
  PhFileZip,
  PhFileImage,
  PhFileVideo,
  PhFileText,
  PhLinkBreak,
} from '@phosphor-icons/vue'
const props = defineProps<{ name: string; kind?: string; index?: number }>()
const extension = computed(() => props.name.split('.').pop()?.toLowerCase() || '')
const icon = computed(() => {
  if (props.kind === 'directory') return PhFolderSimple
  if (props.kind === 'blocked') return PhLinkBreak
  if (extension.value === 'pdf') return PhFilePdf
  if (['zip', 'rar', '7z', 'tar', 'gz'].includes(extension.value)) return PhFileZip
  if (['jpg', 'jpeg', 'png', 'webp', 'gif'].includes(extension.value)) return PhFileImage
  if (['mp4', 'mkv', 'mov', 'avi'].includes(extension.value)) return PhFileVideo
  if (['txt', 'md', 'csv', 'json', 'epub'].includes(extension.value)) return PhFileText
  return PhFile
})
const color = computed(() => {
  if (props.kind === 'directory') {
    return ['blue', 'red', 'purple', 'green', 'yellow'][(props.index || 0) % 5]
  }
  if (extension.value === 'pdf') return 'red'
  if (['zip', 'rar', '7z'].includes(extension.value)) return 'yellow'
  if (['jpg', 'jpeg', 'png', 'webp'].includes(extension.value)) return 'cyan'
  if (['mp4', 'mkv', 'mov', 'epub'].includes(extension.value)) return 'purple'
  return 'slate'
})
</script>
<template>
  <component :is="icon" weight="fill" :class="['file-icon', 'color-' + color]" aria-hidden="true" />
</template>
