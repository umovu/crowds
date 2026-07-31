<template>
  <!-- Preview of the results + full-page chat screens with canned personas.
       No backend, no LLM calls — for looking at the layout only. -->
  <FlowResults
    mode="panel"
    demo
    :query="query"
    @back="$router.push('/')"
  />
</template>

<script setup>
import FlowResults from '../components/flow/FlowResults.vue'

const query = 'A startup investing app where you can start from R50 a month.'
</script>
