// app/static/app.js
const form = document.getElementById('word-form')
const input = document.getElementById('word-input')
const submitBtn = document.getElementById('submit-btn')
const clearBtn = document.getElementById('clear-btn')
const sampleBtn = document.getElementById('sample-btn')
const wordCounter = document.getElementById('word-counter')

const resultCard = document.getElementById('result-card')
const wordDisplay = document.getElementById('word-display')
const decodeDisplay = document.getElementById('decode-display')
const syllableCount = document.getElementById('syllable-count')
const stressIndex = document.getElementById('stress-index')
const cefrBadge = document.getElementById('cefr-badge')

const bulkResultsPanel = document.getElementById('bulk-results')
const bulkCountHeading = document.getElementById('bulk-count-heading')
const bulkGrid = document.getElementById('bulk-grid')
const copyAllBtn = document.getElementById('copy-all-btn')
const downloadTxtBtn = document.getElementById('download-txt-btn')
const downloadCsvBtn = document.getElementById('download-csv-btn')
const errorBanner = document.getElementById('error-banner')
const errorMessage = document.getElementById('error-message')

let lastProcessedResults = []

const isDevEnvironment = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'

const normalizeDisplayText = (value) =>
  String(value || '')
    .replace(/["']/g, '')
    .replace(/\s+|·/g, '-')
    .replace(/-+/g, '-')
    .replace(/^-|-$/g, '')

const getCefrColor = (cefr) => {
  const map = {
    A1: '#0f9d58', A2: '#0f9d58', B1: '#ef8f20', B2: '#ef8f20', C1: '#d93025', C2: '#d93025'
  }
  return map[cefr] || '#0f9d58'
}

const autoResizeTextarea = () => {
  if (!input) return
  input.style.height = 'auto'
  input.style.height = `${Math.max(54, input.scrollHeight)}px`
}

const parseWordsFromInput = (text) => {
  return String(text || '').split(/[\r\n,;\t\s]+/).map((w) => w.trim()).filter((w) => w.length > 0)
}

const updateWordCounter = () => {
  const count = parseWordsFromInput(input.value).length
  if (count === 0) wordCounter.textContent = '0 words detected'
  else if (count === 1) wordCounter.textContent = '1 word ready to analyze'
  else wordCounter.textContent = `${count} words detected (bulk mode)`
}

input.addEventListener('input', () => { autoResizeTextarea(); updateWordCounter() })
input.addEventListener('paste', () => { setTimeout(() => { autoResizeTextarea(); updateWordCounter() }, 0) })

input.addEventListener('keydown', (event) => {
  if (event.key === 'Enter' && !event.shiftKey && parseWordsFromInput(input.value).length <= 1) {
    event.preventDefault(); form.requestSubmit()
  } else if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) {
    event.preventDefault(); form.requestSubmit()
  }
})

if (clearBtn) {
  clearBtn.addEventListener('click', () => {
    input.value = ''; autoResizeTextarea(); updateWordCounter()
    resultCard.classList.add('hidden'); bulkResultsPanel.classList.add('hidden'); errorBanner.classList.add('hidden')
    lastProcessedResults = []; input.focus()
  })
}

if (sampleBtn) {
  sampleBtn.addEventListener('click', () => {
    input.value = ['english', 'resignation', 'aqueous', 'accurately', 'additionally'].join('\n')
    autoResizeTextarea(); updateWordCounter(); form.requestSubmit()
  })
}

const renderSingleResult = (data) => {
  hideError(); bulkResultsPanel.classList.add('hidden'); resultCard.classList.remove('hidden')
  wordDisplay.textContent = normalizeDisplayText(data.word)
  decodeDisplay.textContent = normalizeDisplayText(data.decoding || data.formatted || data.word)
  syllableCount.textContent = Array.isArray(data.syllables) ? data.syllables.length : 1
  stressIndex.textContent = String(data.stressed_syllable_index ?? 0)
  const cefr = data.cefr || 'A1'
  cefrBadge.textContent = cefr
  const color = getCefrColor(cefr)
  cefrBadge.style.background = `${color}22`; cefrBadge.style.color = color
  lastProcessedResults = [data]
}

const renderBulkResults = (results) => {
  hideError(); resultCard.classList.add('hidden'); bulkResultsPanel.classList.remove('hidden')
  bulkCountHeading.textContent = `Processed ${results.length} words`
  bulkGrid.innerHTML = ''
  lastProcessedResults = results
  results.forEach((item) => {
    const card = document.createElement('div'); card.className = 'bulk-card'
    const color = getCefrColor(item.cefr || 'A1')
    card.innerHTML = `
      <div class="bulk-card-top">
        <span class="bulk-word-raw">${normalizeDisplayText(item.word)}</span>
        <span class="badge" style="background: ${color}22; color: ${color};">${item.cefr || 'A1'}</span>
      </div>
      <div class="bulk-decoding">${normalizeDisplayText(item.decoding || item.formatted || item.word)}</div>
      <div class="bulk-card-meta">
        <span>Syllables: <strong>${Array.isArray(item.syllables) ? item.syllables.length : 1}</strong></span>
        <span>Stress index: <strong>${item.stressed_syllable_index ?? 0}</strong></span>
      </div>
    `
    bulkGrid.appendChild(card)
  })
}

const fetchAnalysis = async (wordsRaw) => {
  const wordsList = parseWordsFromInput(wordsRaw)
  if (wordsList.length === 0) throw new Error('Please enter at least one word.')
  let endpoint = '/api/analyze'
  if (isDevEnvironment) {
    endpoint += '?bypass=true'
    console.log('🔧 Dev Override: Forcing live engine rules via URL args.')
  }

  const response = await fetch(endpoint, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(wordsList.length === 1 ? { word: wordsList } : { words: wordsList })
  })
  const data = await response.json()
  if (!response.ok) throw new Error(data.error || 'Failed to analyze words.')
  return data
}

form.addEventListener('submit', async (e) => {
  e.preventDefault(); const raw = input.value.trim(); if (!raw) return
  submitBtn.disabled = true; submitBtn.querySelector('.btn-text-label').textContent = 'Analyzing…'
  try {
    const data = await fetchAnalysis(raw)
    if (data.results && Array.isArray(data.results)) {
      if (data.results.length === 1) renderSingleResult(data.results[0])
      else renderBulkResults(data.results)
    }
  } catch (err) {
    showError(err.message); resultCard.classList.add('hidden'); bulkResultsPanel.classList.add('hidden')
  } finally {
    submitBtn.disabled = false; submitBtn.querySelector('.btn-text-label').textContent = 'Analyze'
  }
})

if (copyAllBtn) {
  copyAllBtn.addEventListener('click', () => {
    if (!lastProcessedResults.length) return
    const textLines = lastProcessedResults.map((item) => `${item.word} -> ${normalizeDisplayText(item.decoding || item.formatted || item.word)}`).join('\n')
    navigator.clipboard.writeText(textLines).then(() => {
      const originalText = copyAllBtn.textContent; copyAllBtn.textContent = '✅ Copied!'
      setTimeout(() => { copyAllBtn.textContent = originalText }, 1800)
    })
  })
}

if (downloadTxtBtn) {
  downloadTxtBtn.addEventListener('click', () => {
    if (!lastProcessedResults.length) return
    const textLines = lastProcessedResults.map((item) => `${item.word}\t${normalizeDisplayText(item.decoding || item.formatted || item.word)}\t${item.cefr || 'A1'}`).join('\n')
    const blob = new Blob([textLines], { type: 'text/plain;charset=utf-8' })
    const url = URL.createObjectURL(blob); const a = document.createElement('a'); a.href = url; a.download = 'syllabicator_results.txt'; a.click(); URL.revokeObjectURL(url)
  })
}

if (downloadCsvBtn) {
  downloadCsvBtn.addEventListener('click', () => {
    if (!lastProcessedResults.length) return
    const csvRows = ['Word,Decoding,Syllables,StressIndex,CEFR']
    lastProcessedResults.forEach((item) => {
      const syls = Array.isArray(item.syllables) ? item.syllables.join('-') : item.word
      csvRows.push(`"${item.word}","${normalizeDisplayText(item.decoding || item.formatted || item.word)}","${syls}",${item.stressed_syllable_index ?? 0},"${item.cefr || 'A1'}"`)
    })
    const blob = new Blob([csvRows.join('\n')], { type: 'text/csv;charset=utf-8' })
    const url = URL.createObjectURL(blob); const a = document.createElement('a'); a.href = url; a.download = 'syllabicator_results.csv'; a.click(); URL.revokeObjectURL(url)
  })
}

const showError = (msg) => { errorBanner.classList.remove('hidden'); errorMessage.textContent = msg }
const hideError = () => { errorBanner.classList.add('hidden') }
autoResizeTextarea(); updateWordCounter()
