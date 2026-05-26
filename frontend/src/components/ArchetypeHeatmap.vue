<template>
  <div class="chart-container">
    <h3 class="chart-title">Archetype Activity Heatmap</h3>
    <div ref="chartRef" class="chart-area"></div>
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

const renderChart = () => {
  if (!chartRef.value || !props.data.length) return

  const container = chartRef.value
  container.innerHTML = ''

  // Pivot data: archetypes x rounds
  const archetypes = [...new Set(props.data.map(d => d.archetype))].sort()
  const rounds = [...new Set(props.data.map(d => d.round))].sort((a, b) => a - b)

  const matrix = {}
  props.data.forEach(d => {
    if (!matrix[d.archetype]) matrix[d.archetype] = {}
    matrix[d.archetype][d.round] = d.action_count
  })

  const margin = { top: 20, right: 20, bottom: 40, left: 120 }
  const cellSize = 24
  const width = rounds.length * cellSize
  const height = archetypes.length * cellSize

  const svg = d3.select(container)
    .append('svg')
    .attr('width', width + margin.left + margin.right)
    .attr('height', height + margin.top + margin.bottom)
    .append('g')
    .attr('transform', `translate(${margin.left},${margin.top})`)

  // Scales
  const x = d3.scaleBand()
    .domain(rounds)
    .range([0, width])
    .padding(0.05)

  const y = d3.scaleBand()
    .domain(archetypes)
    .range([0, height])
    .padding(0.05)

  const color = d3.scaleSequential()
    .interpolator(d3.interpolateOranges)
    .domain([0, d3.max(props.data, d => d.action_count) || 1])

  // Cells
  svg.selectAll('.cell')
    .data(props.data)
    .enter()
    .append('rect')
    .attr('class', 'cell')
    .attr('x', d => x(d.round))
    .attr('y', d => y(d.archetype))
    .attr('width', x.bandwidth())
    .attr('height', y.bandwidth())
    .attr('fill', d => color(d.action_count))
    .attr('rx', 3)
    .on('mouseover', function(event, d) {
      d3.select(this).attr('stroke', '#333').attr('stroke-width', 2)
    })
    .on('mouseout', function() {
      d3.select(this).attr('stroke', 'none')
    })

  // Cell labels
  svg.selectAll('.cell-label')
    .data(props.data)
    .enter()
    .append('text')
    .attr('class', 'cell-label')
    .attr('x', d => x(d.round) + x.bandwidth() / 2)
    .attr('y', d => y(d.archetype) + y.bandwidth() / 2)
    .attr('text-anchor', 'middle')
    .attr('dominant-baseline', 'middle')
    .style('font-size', '10px')
    .style('font-family', 'JetBrains Mono, monospace')
    .style('fill', d => d.action_count > (color.domain()[1] / 2) ? '#FFF' : '#333')
    .text(d => d.action_count)

  // X axis
  svg.append('g')
    .attr('transform', `translate(0,${height})`)
    .call(d3.axisBottom(x).tickValues(rounds.filter((_, i) => i % Math.ceil(rounds.length / 10) === 0)))
    .style('font-family', 'JetBrains Mono, monospace')
    .style('font-size', '10px')

  // Y axis
  svg.append('g')
    .call(d3.axisLeft(y))
    .style('font-family', 'Space Grotesk, sans-serif')
    .style('font-size', '11px')

  // Axis labels
  svg.append('text')
    .attr('transform', 'rotate(-90)')
    .attr('y', -margin.left + 10)
    .attr('x', -height / 2)
    .attr('text-anchor', 'middle')
    .style('font-size', '11px')
    .style('fill', '#999')
    .text('Archetype')

  svg.append('text')
    .attr('x', width / 2)
    .attr('y', height + margin.bottom - 5)
    .attr('text-anchor', 'middle')
    .style('font-size', '11px')
    .style('fill', '#999')
    .text('Round')
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
  overflow-x: auto;
}

.chart-title {
  font-family: 'JetBrains Mono', monospace;
  font-size: 14px;
  font-weight: 700;
  margin: 0 0 16px 0;
}

.chart-area {
  min-height: 200px;
}
</style>
