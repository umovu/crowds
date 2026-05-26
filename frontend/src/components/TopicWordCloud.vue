<template>
  <div class="chart-container">
    <h3 class="chart-title">Topic Landscape</h3>
    <div ref="chartRef" class="chart-area"></div>
    <div class="topic-legend">
      <div class="legend-item">
        <span class="legend-dot economy"></span>
        <span>Economy</span>
      </div>
      <div class="legend-item">
        <span class="legend-dot security"></span>
        <span>Security</span>
      </div>
      <div class="legend-item">
        <span class="legend-dot social"></span>
        <span>Social</span>
      </div>
      <div class="legend-item">
        <span class="legend-dot politics"></span>
        <span>Politics</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, watch } from 'vue'
import * as d3 from 'd3'

const props = defineProps({
  data: {
    type: Array,
    default: () => []
  }
})

const chartRef = ref(null)

const getCategoryColor = (topic) => {
  const t = topic.toLowerCase()
  if (['grant', 'sassa', 'eskom', 'load-shedding', 'electricity', 'power', 'economic', 'business', 'money', 'job'].some(w => t.includes(w))) {
    return '#4ECDC4'
  }
  if (['police', 'saps', 'security', 'violence', 'crime', 'gang', 'protest', 'unrest'].some(w => t.includes(w))) {
    return '#FF6B6B'
  }
  if (['land', 'housing', 'health', 'education', 'community', 'family', 'women', 'children'].some(w => t.includes(w))) {
    return '#95E1D3'
  }
  if (['anc', 'da', 'eff', 'political', 'government', 'policy', 'parliament', 'election'].some(w => t.includes(w))) {
    return '#FFD93D'
  }
  return '#A8D8EA'
}

const renderChart = () => {
  if (!chartRef.value || !props.data.length) return

  const container = chartRef.value
  container.innerHTML = ''

  const width = container.clientWidth
  const height = 350

  const svg = d3.select(container)
    .append('svg')
    .attr('width', width)
    .attr('height', height)

  // Pack layout
  const root = d3.hierarchy({ children: props.data })
    .sum(d => d.total_mentions)

  const pack = d3.pack()
    .size([width, height])
    .padding(10)

  pack(root)

  const nodes = root.leaves()

  // Draw bubbles
  const groups = svg.selectAll('.bubble')
    .data(nodes)
    .enter()
    .append('g')
    .attr('class', 'bubble')
    .attr('transform', d => `translate(${d.x},${d.y})`)

  groups.append('circle')
    .attr('r', 0)
    .attr('fill', d => getCategoryColor(d.data.topic))
    .attr('opacity', 0.8)
    .transition()
    .duration(800)
    .attr('r', d => d.r)

  groups.append('text')
    .attr('text-anchor', 'middle')
    .attr('dominant-baseline', 'middle')
    .style('font-family', 'Space Grotesk, sans-serif')
    .style('font-size', d => Math.min(d.r / 2.5, 14) + 'px')
    .style('font-weight', '600')
    .style('fill', '#333')
    .style('pointer-events', 'none')
    .text(d => d.data.topic.length > 12 ? d.data.topic.slice(0, 10) + '...' : d.data.topic)

  // Tooltip
  const tooltip = d3.select(container)
    .append('div')
    .attr('class', 'chart-tooltip')
    .style('opacity', 0)

  groups.on('mouseover', function(event, d) {
    d3.select(this).select('circle').attr('opacity', 1).attr('stroke', '#333').attr('stroke-width', 2)
    tooltip.transition().duration(200).style('opacity', 1)
    tooltip.html(`
      <strong>${d.data.topic}</strong><br/>
      Mentions: ${d.data.total_mentions}<br/>
      First seen: Round ${d.data.first_round}<br/>
      Peak: Round ${d.data.peak_round} (${d.data.peak_count})<br/>
      Trend: ${d.data.trend}
    `)
    .style('left', (event.pageX + 10) + 'px')
    .style('top', (event.pageY - 28) + 'px')
  })
  .on('mouseout', function() {
    d3.select(this).select('circle').attr('opacity', 0.8).attr('stroke', 'none')
    tooltip.transition().duration(500).style('opacity', 0)
  })
}

onMounted(renderChart)
watch(() => props.data, renderChart, { deep: true })
</script>

<style scoped>
.chart-container {
  background: #FFF;
  border: 1px solid #EAEAEA;
  border-radius: 8px;
  padding: 20px;
}

.chart-title {
  font-family: 'JetBrains Mono', monospace;
  font-size: 14px;
  font-weight: 700;
  margin: 0 0 16px 0;
}

.chart-area {
  width: 100%;
  height: 350px;
  position: relative;
}

.topic-legend {
  display: flex;
  gap: 20px;
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid #F0F0F0;
}

.legend-item {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: #666;
}

.legend-dot {
  width: 12px;
  height: 12px;
  border-radius: 50%;
}

.legend-dot.economy { background: #4ECDC4; }
.legend-dot.security { background: #FF6B6B; }
.legend-dot.social { background: #95E1D3; }
.legend-dot.politics { background: #FFD93D; }

:deep(.chart-tooltip) {
  position: absolute;
  background: #FFF;
  border: 1px solid #EAEAEA;
  border-radius: 6px;
  padding: 12px;
  font-size: 12px;
  box-shadow: 0 4px 12px rgba(0,0,0,0.1);
  pointer-events: none;
  z-index: 100;
  font-family: 'Space Grotesk', sans-serif;
}
</style>
