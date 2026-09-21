<template>
  <section class="findings" v-if="findings">
    <p v-if="findings.brief_edited" class="edited">Brief was corrected before the run.</p>

    <h2 class="count">
      {{ findings.understood }} of {{ findings.total }} understood the ask.
    </h2>

    <div v-if="findings.worst_misread" class="block">
      <h3>Worst misreading</h3>
      <blockquote>
        “{{ findings.worst_misread.words }}”
      </blockquote>
      <p class="who" v-if="findings.worst_misread.name">
        {{ findings.worst_misread.name }}
        <span v-if="findings.worst_misread.segment"> · {{ findings.worst_misread.segment }}</span>
        <span v-if="findings.worst_misread.label"> · thought: {{ findings.worst_misread.label }}</span>
      </p>
    </div>

    <div v-if="findings.misreads?.length" class="block">
      <h3>Misread map</h3>
      <div v-for="group in findings.misreads" :key="group.label" class="group">
        <p class="group-title">
          {{ group.count }} thought <strong>{{ group.label }}</strong>
        </p>
        <ul>
          <li v-for="(w, i) in group.words" :key="i">“{{ w }}”</li>
        </ul>
      </div>
    </div>

    <div v-if="findings.split" class="block split">
      <h3>Split ask</h3>
      <p>
        {{ findings.primary_count }} said {{ findings.primary }},
        {{ findings.secondary_count }} said {{ findings.secondary }}.
        Your poster says both.
      </p>
    </div>

    <div v-if="findings.claims_landed?.length" class="block">
      <h3>Implied claims that landed as fact</h3>
      <ul>
        <li v-for="c in findings.claims_landed" :key="c">{{ c }}</li>
      </ul>
    </div>

    <div v-if="findings.trust_blockers?.length" class="block">
      <h3>Top trust blockers</h3>
      <ol>
        <li v-for="t in findings.trust_blockers" :key="t">{{ t }}</li>
      </ol>
    </div>

    <div v-if="findings.attention" class="block">
      <h3>Attention (stated)</h3>
      <p>
        {{ findings.attention.said_they_would_stop }} said they would stop.
        {{ findings.attention.said_they_would_keep_going }} said they would keep going.
      </p>
    </div>

    <p class="caveat">
      {{ findings.caveat || 'This measures comprehension and stated reaction. It does not predict sales.' }}
    </p>
  </section>
</template>

<script setup>
defineProps({
  findings: { type: Object, default: null },
})
</script>

<style scoped>
.findings {
  margin-top: 28px;
  padding: 20px;
  border: 1px solid #e3e8e5;
  border-radius: 10px;
  background: #fbfcfb;
}
.edited {
  color: #666;
  font-size: 13px;
  margin: 0 0 12px;
}
.count {
  font-size: 22px;
  margin: 0 0 18px;
  color: #1a1a1a;
  text-transform: none;
  letter-spacing: 0;
}
.block { margin: 0 0 18px; }
h3 {
  font-size: 13px;
  text-transform: uppercase;
  letter-spacing: .06em;
  color: #666;
  margin: 0 0 8px;
}
blockquote {
  margin: 0;
  padding: 12px 14px;
  background: #fff;
  border-left: 3px solid #1E9E5A;
  border-radius: 0 8px 8px 0;
  line-height: 1.5;
}
.who { color: #666; font-size: 13px; margin: 8px 0 0; }
.group { margin: 0 0 12px; }
.group-title { margin: 0 0 4px; }
ul, ol { margin: 0; padding-left: 20px; line-height: 1.7; }
.caveat {
  margin: 20px 0 0;
  padding: 12px 14px;
  background: #eef7f1;
  border: 1px solid #cfe6d8;
  border-radius: 8px;
  color: #1a1a1a;
  font-size: 14px;
  line-height: 1.5;
}
</style>
