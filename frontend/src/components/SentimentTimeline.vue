<template>
  <div class="chart-container">
    <h3 class="chart-title">Sentiment Timeline</h3>
    <div ref="chartRef" class="chart-area"></div>
    <div class="chart-legend">
      <div class="legend-item">
        <span class="legend-line impact"></span>
        <span>Avg Impact</span>
      </div>
      <div class="legend-item">
        <span class="legend-line radicalism"></span>
        <span>Avg Radicalism</span>
      </div>
      <div class="legend-item">
        <span class="legend-dot event"></span>
        <span>Event Injected</span>
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

const renderChart = () => {
  if (!chartRef.value || !props.data.length) return

  const container = chartRef.value
  container.innerHTML = ''

  const margin = { top: 20, right: 30, bottom: 40, left: 50 }
  const width = container.clientWidth - margin.left - margin.right
  const height = 300 - margin.top - margin.bottom

  const svg = d3.select(container)
    .append('svg')
    .attr('width', width + margin.left + margin.right)
    .attr('height', height + margin.top + margin.bottom)
    .append('g')
    .attr('transform', `translate(${margin.left},${margin.top})`)

  // Scales
  const x = d3.scaleLinear()
    .domain([0, props.data.length - 1])
    .range([0, width])

  const y = d3.scaleLinear()
    .domain([0, 5])
    .range([height, 0])

  // Axes
  svg.append('g')
    .attr('transform', `translate(0,${height})`)
    .call(d3.axisBottom(x).ticks(Math.min(props.data.length, 10)).tickFormat(d => `R${d}`))
    .style('font-family', 'JetBrains Mono, monospace')
    .style('font-size', '11px')

  svg.append('g')
    .call(d3.axisLeft(y).ticks(5))
    .style('font-family', 'JetBrains Mono, monospace')
    .style('font-size', '11px')

  // Grid lines
  svg.append('g')
    .attr('class', 'grid')
    .call(d3.axisLeft(y).ticks(5).tickSize(-width).tickFormat(''))
    .style('stroke-dasharray', '2,2')
    .style('stroke-opacity', 0.1)

  // Line generators
  const impactLine = d3.line()
    .x(d => x(d.round))
    .y(d => y(d.avg_impact))
    .curve(d3.curveMonotoneX)

  const radicalismLine = d3.line()
    .x(d => x(d.round))
    .y(d => y(d.avg_radicalism))
    .curve(d3.curveMonotoneX)

  // Draw lines
  svg.append('path')
    .datum(props.data)
    .attr('fill', 'none')
    .attr('stroke', '#FF6B6B')
    .attr('stroke-width', 2)
    .attr('d', impactLine)

  svg.append('path')
    .datum(props.data)
    .attr('fill', 'none')
    .attr('stroke', '#4ECDC4')
    .attr('stroke-width', 2)
    .attr('d', radicalismLine)

  // Event markers
  const eventRounds = props.data.filter(d => d.events && d.events.length > 0)
  
  svg.selectAll('.event-marker')
    .data(eventRounds)
    .enter()
    .append('line')
    .attr('class', 'event-marker')
    .attr('x1', d => x(d.round))
    .attr('x2', d => x(d.round))
    .attr('y1', 0)
    .attr('y2', height)
    .attr('stroke', '#FFD93D')
    .attr('stroke-width', 2)
    .attr('stroke-dasharray', '4,4')
    .attr('opacity', 0.7)

  // Event dots
  svg.selectAll('.event-dot')
    .data(eventRounds)
    .enter()
    .append('circle')
    .attr('class', 'event-dot')
    .attr('cx', d => x(d.round))
    .attr('cy', 10)
    .attr('r', 6)
    .attr('fill', '#FFD93D')
    .attr('stroke', '#FFF')
    .attr('stroke-width', 2)

  // Tooltip
  const tooltip = d3.select(container)
    .append('div')
    .attr('class', 'chart-tooltip')
    .style('opacity', 0)

  svg.selectAll('.hover-dot')
    .data(props.data)
    .enter()
    .append('circle')
    .attr('class', 'hover-dot')
    .attr('cx', d => x(d.round))
    .attr('cy', d => y(d.avg_impact))
    .attr('r', 4)
    .attr('fill', '#FF6B6B')
    .attr('opacity', 0)
    .on('mouseover', function(event, d) {
      d3.select(this).attr('opacity', 1)
      tooltip.transition().duration(200).style('opacity', 1)
      tooltip.html(`
        <strong>Round ${d.round}</strong><br/>
        Avg Impact: ${d.avg_impact?.toFixed(2) || 0}<br/>
        Avg Radicalism: ${d.avg_radicalism?.toFixed(2) || 0}<br/>
        Non-participation: ${((d.non_participation_pct || 0) * 100).toFixed(0)}%<br/>
        ${d.events?.length ? 'Events: ' + d.events.map(e => e.title).join(', ') : ''}
      `)
      .style('left', (event.pageX + 10) + 'px')
      .style('top', (event.pageY - 28) + 'px')
    })
    .on('mouseout', function() {
      d3.select(this).attr('opacity', 0)
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
  height: 300px;
  position: relative;
}

.chart-legend {
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

.legend-line {
  width: 20px;
  height: 3px;
  border-radius: 2px;
}

.legend-line.impact { background: #FF6B6B; }
.legend-line.radicalism { background: #4ECDC4; }

.legend-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: #FFD93D;
  border: 2px solid #FFF;
  box-shadow: 0 0 0 1px #E0E0E0;
}

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
