<!--
  LensIcon — the line icons that sit at the head of each pointer row.

  Traced from the Study.dc.html design canvas (claude.ai design project
  f01be819-6266-4989-81eb-3a6a00f0ba6d): 24-box, 1.5 stroke, no fill, colour
  inherited from the row so hover/active states need no extra rules here.

  `name` is a pointer id from LENS_CARDS, or 'sub' for the speech bubble used
  on the sub-question rows.
-->
<template>
  <svg
    class="lens-icon"
    :width="size"
    :height="size"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    stroke-width="1.5"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
  >
    <!-- Test how a message lands — speech bubble, understood -->
    <template v-if="name === 'land'">
      <path d="M4 5.5h16v10H9.5L6 19v-3.5H4z" />
      <path d="M9 10l2 2 3.5-4" />
    </template>

    <!-- Find what stops people saying yes — the blocked circle -->
    <template v-else-if="name === 'breaks'">
      <circle cx="12" cy="12" r="8" />
      <path d="M6.4 6.4l11.2 11.2" />
    </template>

    <!-- Find out which group it's for — the globe, i.e. which slice of it -->
    <template v-else-if="name === 'fit'">
      <circle cx="12" cy="12" r="8" />
      <path d="M4 12h16M12 4c2.9 2.8 2.9 13.2 0 16M12 4c-2.9 2.8-2.9 13.2 0 16" />
    </template>

    <!-- Compare two ways of saying it — A against B -->
    <template v-else-if="name === 'ab'">
      <circle cx="6.5" cy="12" r="3" />
      <path d="M10.5 6.5l3 11" />
      <rect x="15" y="9" width="6" height="6" rx="1" />
    </template>

    <!-- Test a poster before you print it — the picture frame -->
    <template v-else-if="name === 'poster'">
      <rect x="3" y="4" width="18" height="16" rx="2" />
      <circle cx="8.5" cy="9" r="1.3" />
      <path d="M4.5 17l4.5-4.5 3.5 3.5 3-3 4 4" />
    </template>

    <!-- Test a page on your website — the browser chrome -->
    <template v-else-if="name === 'website'">
      <rect x="3" y="5" width="18" height="14" rx="2" />
      <path d="M3 9h18" />
      <circle cx="9.5" cy="14" r="2.1" />
      <path d="M11.2 15.7L13 17.5" />
    </template>

    <!-- Sub-question — a plain speech bubble, one level quieter -->
    <template v-else>
      <path d="M4 5.5h16v10H9.5L6 19v-3.5H4z" />
    </template>
  </svg>
</template>

<script setup>
defineProps({
  name: { type: String, default: 'sub' },
  size: { type: [Number, String], default: 21 },
})
</script>

<style scoped>
.lens-icon { flex: none; display: block; }
</style>
