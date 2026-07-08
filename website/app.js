// Global App State
let appData = null;
let activeView = 'dashboard';
let activeTestCase = null;
let activeModel = null;
let activeTimelineStep = 0;
let playbackInterval = null;
let playbackSpeed = 1000; // ms per step

// Chart Instances
let accuracyChartInstance = null;
let latencyChartInstance = null;

// DOM Elements
const views = {
  dashboard: document.getElementById('view-dashboard'),
  'test-cases': document.getElementById('view-test-cases'),
  visualizer: document.getElementById('view-visualizer')
};

const navButtons = {
  dashboard: document.getElementById('nav-dashboard-btn'),
  'test-cases': document.getElementById('nav-testcases-btn'),
  visualizer: document.getElementById('nav-visualizer-btn')
};

// Initialize Application
document.addEventListener('DOMContentLoaded', () => {
  setupNavigation();
  setupFilters();
  setupVisualizerControls();
  setupLogsCollapsibles();
  
  // Load data
  loadBenchmarkData();
  
  // Reload button
  document.getElementById('reload-data-btn').addEventListener('click', () => {
    loadBenchmarkData();
  });
});

// Setup Views and Navigation
function setupNavigation() {
  Object.keys(navButtons).forEach(viewName => {
    navButtons[viewName].addEventListener('click', () => {
      switchView(viewName);
    });
  });
}

function switchView(viewName) {
  activeView = viewName;
  
  // Update nav buttons active state
  Object.keys(navButtons).forEach(name => {
    if (name === viewName) {
      navButtons[name].classList.add('active');
    } else {
      navButtons[name].classList.remove('active');
    }
  });
  
  // Update views visibility
  Object.keys(views).forEach(name => {
    if (name === viewName) {
      views[name].classList.add('active');
    } else {
      views[name].classList.remove('active');
    }
  });

  // Update Page Header Title & Subtitle
  const pageTitle = document.getElementById('page-title');
  const pageSubtitle = document.getElementById('page-subtitle');
  
  if (viewName === 'dashboard') {
    pageTitle.textContent = 'Benchmark Dashboard';
    pageSubtitle.textContent = 'Comparative analysis of language model performance on pathfinding rulesets.';
    // Redraw charts to ensure responsive scaling
    renderCharts();
  } else if (viewName === 'test-cases') {
    pageTitle.textContent = 'Test Cases Explorer';
    pageSubtitle.textContent = 'Browse individual game instances and compare model pathfinding results.';
    renderTestCases();
  } else if (viewName === 'visualizer') {
    pageTitle.textContent = 'Interactive Game Board';
    pageSubtitle.textContent = 'Visualize model paths, portal teleports, and wind gusts turn-by-turn.';
    
    // If no test case is active, select the first one
    if (!activeTestCase && appData && appData.test_cases && appData.test_cases.length > 0) {
      selectTestCase(appData.test_cases[0].id);
    } else {
      initVisualizer();
    }
  }
}

// Fetch JSON data
async function loadBenchmarkData() {
  try {
    const response = await fetch('results_data.json');
    if (!response.ok) {
      throw new Error(`Failed to load benchmark data: ${response.statusText}`);
    }
    appData = await response.json();
    console.log("Benchmark data loaded successfully:", appData);
    
    // Initialize Dashboard
    populateDashboardStats();
    renderCharts();
    populateModelsSummaryTable();
    
    // Initialize filters options based on models
    populateModelFilterDropdown();
    
    // Switch to active view
    switchView(activeView);
  } catch (error) {
    console.error("Error loading benchmark data:", error);
    alert("Could not load results_data.json. Please ensure update_results.py has been run.");
  }
}

// Dashboard Calculations & Display
function populateDashboardStats() {
  if (!appData) return;
  
  document.getElementById('stat-total-games').textContent = appData.summary.total_games;
  document.getElementById('stat-total-models').textContent = appData.summary.models_count;
  
  // Calculate average accuracy across all models
  const models = Object.values(appData.models);
  if (models.length > 0) {
    const avgAccuracy = models.reduce((acc, m) => acc + m.accuracy, 0) / models.length;
    document.getElementById('stat-avg-accuracy').textContent = `${(avgAccuracy * 100).toFixed(0)}%`;
    
    // Find fastest model
    const fastest = models.reduce((prev, current) => {
      return (prev.avg_latency < current.avg_latency) ? prev : current;
    });
    // Truncate name for card display
    const shortName = fastest.model_name.split('/').pop().split(':').shift();
    document.getElementById('stat-fastest-model').textContent = shortName;
  }
}

function populateModelsSummaryTable() {
  const tbody = document.querySelector('#models-summary-table tbody');
  if (!tbody || !appData) return;
  
  tbody.innerHTML = '';
  
  Object.values(appData.models).forEach(model => {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td class="model-name-cell"><i class="fa-solid fa-microchip icon-muted"></i> ${model.model_name}</td>
      <td><span class="badge ${model.accuracy === 1 ? 'badge-success' : 'badge-warning'}">${(model.accuracy * 100).toFixed(1)}%</span></td>
      <td>${(model.exact_match_rate * 100).toFixed(1)}%</td>
      <td>${(model.optimal_rate * 100).toFixed(1)}%</td>
      <td><i class="fa-regular fa-clock icon-muted"></i> ${model.avg_latency.toFixed(2)}s</td>
      <td>${model.total_cases}</td>
    `;
    tbody.appendChild(tr);
  });
}

function renderCharts() {
  if (!appData) return;
  
  const models = Object.values(appData.models);
  const labels = models.map(m => m.model_name.split('/').pop()); // Show short name
  const accuracyData = models.map(m => m.accuracy * 100);
  const optimalData = models.map(m => m.optimal_rate * 100);
  const latencyData = models.map(m => m.avg_latency);
  
  // Destroy previous charts if they exist
  if (accuracyChartInstance) accuracyChartInstance.destroy();
  if (latencyChartInstance) latencyChartInstance.destroy();
  
  // Style defaults for Dark Theme
  Chart.defaults.color = '#9ca3af';
  Chart.defaults.borderColor = 'rgba(255, 255, 255, 0.08)';
  Chart.defaults.font.family = "'Inter', sans-serif";
  
  // Accuracy Chart
  const ctxAcc = document.getElementById('accuracy-chart').getContext('2d');
  accuracyChartInstance = new Chart(ctxAcc, {
    type: 'bar',
    data: {
      labels: labels,
      datasets: [
        {
          label: 'Valid Paths %',
          data: accuracyData,
          backgroundColor: 'rgba(139, 92, 246, 0.65)',
          borderColor: '#8b5cf6',
          borderWidth: 1,
          borderRadius: 6
        },
        {
          label: 'Optimal Paths %',
          data: optimalData,
          backgroundColor: 'rgba(16, 185, 129, 0.65)',
          borderColor: '#10b981',
          borderWidth: 1,
          borderRadius: 6
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        y: {
          beginAtZero: true,
          max: 100,
          grid: { color: 'rgba(255, 255, 255, 0.05)' }
        },
        x: {
          grid: { display: false }
        }
      },
      plugins: {
        legend: { position: 'bottom' }
      }
    }
  });
  
  // Latency Chart
  const ctxLat = document.getElementById('latency-chart').getContext('2d');
  latencyChartInstance = new Chart(ctxLat, {
    type: 'bar',
    data: {
      labels: labels,
      datasets: [{
        label: 'Avg Latency (Seconds)',
        data: latencyData,
        backgroundColor: 'rgba(6, 182, 212, 0.65)',
        borderColor: '#06b6d4',
        borderWidth: 1,
        borderRadius: 6
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        y: {
          beginAtZero: true,
          grid: { color: 'rgba(255, 255, 255, 0.05)' }
        },
        x: {
          grid: { display: false }
        }
      },
      plugins: {
        legend: { position: 'bottom' }
      }
    }
  });
}

// VIEW 2: Test Cases Filters & List
function setupFilters() {
  const searchInput = document.getElementById('filter-search');
  const diffSelect = document.getElementById('filter-difficulty');
  const statusSelect = document.getElementById('filter-status');
  
  searchInput.addEventListener('input', renderTestCases);
  diffSelect.addEventListener('change', renderTestCases);
  statusSelect.addEventListener('change', renderTestCases);
}

function populateModelFilterDropdown() {
  // We can filter by model in future if we want, but currently we filter by general stats
}

function renderTestCases() {
  const container = document.getElementById('test-cases-list');
  if (!container || !appData) return;
  
  const searchQuery = document.getElementById('filter-search').value.toLowerCase();
  const difficultyFilter = document.getElementById('filter-difficulty').value;
  const statusFilter = document.getElementById('filter-status').value;
  
  container.innerHTML = '';
  
  const filtered = appData.test_cases.filter(tc => {
    // 1. Search Query (id or prompt description)
    const matchesSearch = tc.id.toLowerCase().includes(searchQuery) || 
                          tc.prompt.toLowerCase().includes(searchQuery);
    
    // 2. Difficulty Filter
    const matchesDiff = difficultyFilter === 'all' || tc.difficulty === difficultyFilter;
    
    // 3. Status Filter
    let matchesStatus = true;
    const runs = Object.values(tc.results);
    
    if (statusFilter === 'correct') {
      // All runs are correct
      matchesStatus = runs.every(r => r.correct);
    } else if (statusFilter === 'incorrect') {
      // Any run failed
      matchesStatus = runs.some(r => !r.correct);
    } else if (statusFilter === 'exact') {
      // Any run matches expected output exactly
      matchesStatus = runs.some(r => r.exact);
    }
    
    return matchesSearch && matchesDiff && matchesStatus;
  });
  
  if (filtered.length === 0) {
    container.innerHTML = `
      <div style="grid-column: 1/-1; text-align: center; padding: 3rem; color: var(--text-muted);">
        <i class="fa-solid fa-magnifying-glass fa-2x"></i>
        <p style="margin-top: 1rem;">No test cases match the active filters.</p>
      </div>
    `;
    return;
  }
  
  filtered.forEach(tc => {
    const card = document.createElement('div');
    card.className = 'game-card';
    card.addEventListener('click', () => {
      selectTestCase(tc.id);
      switchView('visualizer');
    });
    
    const portalCount = tc.game.portals ? tc.game.portals.length : 0;
    const blockedCount = tc.game.blocked ? tc.game.blocked.length : 0;
    const windText = tc.game.wind ? `${tc.game.wind.move.name} (T%${tc.game.wind.period}=0)` : 'None';
    
    // Build mini model results indicators
    let resultsHtml = '';
    Object.entries(tc.results).forEach(([modelName, res]) => {
      const shortName = modelName.split('/').pop().split(':').shift();
      const statusClass = res.correct ? 'correct' : 'failed';
      const statusText = res.correct ? 'OK' : 'FAIL';
      resultsHtml += `
        <span class="avatar-result ${statusClass}" title="${modelName}">
          ${shortName}: ${statusText}
        </span>
      `;
    });
    
    card.innerHTML = `
      <div class="game-card-header">
        <span class="badge ${getDifficultyBadgeClass(tc.difficulty)}">${tc.difficulty}</span>
        <span class="game-card-title">${tc.id}</span>
      </div>
      <div class="game-card-body">
        <p>${tc.prompt.substring(0, 110)}...</p>
        <div class="spec-brief">
          <span class="brief-item">Grid: <strong>${tc.game.height}x${tc.game.width}</strong></span>
          <span class="brief-item">Portals: <strong>${portalCount}</strong></span>
          <span class="brief-item">Blocked: <strong>${blockedCount}</strong></span>
          <span class="brief-item">Wind: <strong>${windText}</strong></span>
        </div>
      </div>
      <div class="game-card-footer">
        <span style="font-size: 0.75rem; color: var(--text-muted);">Shortest path: ${tc.answer.turns} turns</span>
        <div class="model-results-avatars">
          ${resultsHtml}
        </div>
      </div>
    `;
    
    container.appendChild(card);
  });
}

function getDifficultyBadgeClass(diff) {
  if (diff === 'easy') return 'badge-success';
  if (diff === 'medium') return 'badge-warning';
  return 'badge-danger';
}

// VIEW 3: Interactive Visualizer Implementation
function selectTestCase(id) {
  if (!appData) return;
  activeTestCase = appData.test_cases.find(tc => tc.id === id);
  
  if (activeTestCase) {
    // Populate model select dropdown
    const modelSelect = document.getElementById('viz-model-select');
    modelSelect.innerHTML = '';
    
    const models = Object.keys(activeTestCase.results);
    models.forEach((modelName, index) => {
      const option = document.createElement('option');
      option.value = modelName;
      option.textContent = modelName;
      if (index === 0) option.selected = true;
      modelSelect.appendChild(option);
    });
    
    activeModel = models[0];
    initVisualizer();
  }
}

function setupVisualizerControls() {
  const modelSelect = document.getElementById('viz-model-select');
  modelSelect.addEventListener('change', (e) => {
    activeModel = e.target.value;
    resetReplayer();
  });
  
  // Playback Controls
  document.getElementById('btn-play-pause').addEventListener('click', togglePlayback);
  document.getElementById('btn-prev-step').addEventListener('click', stepBackward);
  document.getElementById('btn-next-step').addEventListener('click', stepForward);
  document.getElementById('btn-reset-timeline').addEventListener('click', resetReplayer);
  
  const timeline = document.getElementById('step-timeline');
  timeline.addEventListener('input', (e) => {
    setTimelineStep(parseInt(e.target.value));
  });
  
  const speedSelect = document.getElementById('playback-speed');
  speedSelect.addEventListener('change', (e) => {
    playbackSpeed = parseInt(e.target.value);
    if (playbackInterval) {
      // Restart interval with new speed
      clearInterval(playbackInterval);
      playbackInterval = setInterval(stepForward, playbackSpeed);
    }
  });
  
  // Setup tabs
  const tabButtons = document.querySelectorAll('.tab-btn');
  tabButtons.forEach(btn => {
    btn.addEventListener('click', (e) => {
      const targetTab = e.target.dataset.tab;
      
      tabButtons.forEach(b => b.classList.remove('active'));
      e.target.classList.add('active');
      
      document.querySelectorAll('.tab-content').forEach(content => {
        if (content.id === targetTab) {
          content.classList.add('active');
        } else {
          content.classList.remove('active');
        }
      });
    });
  });
}

function setupLogsCollapsibles() {
  const items = [
    { trigger: 'log-prompt-trigger', body: 'log-prompt-body' },
    { trigger: 'log-output-trigger', body: 'log-output-body' },
    { trigger: 'log-reasoning-trigger', body: 'log-reasoning-body' }
  ];
  
  items.forEach(item => {
    const trigger = document.getElementById(item.trigger);
    const body = document.getElementById(item.body);
    const parent = trigger.parentElement;
    
    trigger.addEventListener('click', () => {
      const isOpen = parent.classList.contains('open');
      if (isOpen) {
        parent.classList.remove('open');
      } else {
        parent.classList.add('open');
      }
    });
  });
}

function initVisualizer() {
  if (!activeTestCase) return;
  
  // Fill Specs and IDs
  document.getElementById('viz-game-id').textContent = activeTestCase.id;
  const diffBadge = document.getElementById('viz-game-difficulty');
  diffBadge.textContent = activeTestCase.difficulty;
  diffBadge.className = `badge ${getDifficultyBadgeClass(activeTestCase.difficulty)}`;
  
  // Specifications tab population
  const game = activeTestCase.game;
  document.getElementById('viz-spec-dims').textContent = `${game.height} rows x ${game.width} cols`;
  document.getElementById('viz-spec-start').textContent = `${_spaceToCoordText(game.start, game.width)} (Space ${game.start})`;
  document.getElementById('viz-spec-goal').textContent = `${_spaceToCoordText(game.goal, game.width)} (Space ${game.goal})`;
  document.getElementById('viz-spec-wind').textContent = game.wind ? 
    `${game.wind.move.name} (T%${game.wind.period}=0)` : 'No wind';
    
  // Portals spec list
  const portalsList = document.getElementById('viz-spec-portals');
  portalsList.innerHTML = '';
  if (game.portals && game.portals.length > 0) {
    game.portals.forEach((pair, idx) => {
      const li = document.createElement('li');
      li.className = 'portal-spec-indicator';
      li.innerHTML = `
        <span class="portal-dot" style="background-color: ${getPortalColor(idx)}"></span>
        <span>Space ${pair[0]} ${_spaceToCoordText(pair[0], game.width)} &harr; Space ${pair[1]} ${_spaceToCoordText(pair[1], game.width)}</span>
      `;
      portalsList.appendChild(li);
    });
  } else {
    portalsList.innerHTML = '<li>No portals on this board.</li>';
  }
  
  // Rules cycle tab list
  const rulesList = document.getElementById('viz-spec-rules');
  rulesList.innerHTML = '';
  game.rules.forEach(rule => {
    const item = document.createElement('div');
    item.className = 'rule-cycle-item';
    
    const movesHtml = rule.moves.map(m => `
      <div><strong>"${m.name}"</strong>: (${m.dx > 0 ? m.dx+'E' : m.dx < 0 ? Math.abs(m.dx)+'W' : ''}${m.dy > 0 ? (m.dx!==0?', ':'')+m.dy+'S' : m.dy < 0 ? (m.dx!==0?', ':'')+Math.abs(m.dy)+'N' : ''})</div>
    `).join('');
    
    item.innerHTML = `
      <div class="rule-cycle-title">${rule.label}</div>
      <div class="rule-cycle-moves">${movesHtml}</div>
    `;
    rulesList.appendChild(item);
  });
  
  // Fill Logs tab details
  const modelRes = activeTestCase.results[activeModel];
  document.getElementById('log-prompt-code').textContent = activeTestCase.prompt;
  document.getElementById('log-output-code').textContent = modelRes ? JSON.stringify(JSON.parse(modelRes.output), null, 2) : 'No output log';
  
  // Display reasoning
  const reasoningContainer = document.getElementById('log-reasoning-text');
  if (modelRes && modelRes.reasoning) {
    reasoningContainer.textContent = modelRes.reasoning;
  } else {
    reasoningContainer.innerHTML = `<span style="color: var(--text-muted); font-style: italic;">No provider reasoning logs available.</span>`;
  }
  
  resetReplayer();
}

function resetReplayer() {
  stopPlayback();
  activeTimelineStep = 0;
  
  const modelRes = activeTestCase.results[activeModel];
  const maxSteps = modelRes ? modelRes.replay_path.length : 0;
  
  const timeline = document.getElementById('step-timeline');
  timeline.max = maxSteps;
  timeline.value = 0;
  
  // Refresh code display for selected model logs
  if (modelRes) {
    try {
      document.getElementById('log-output-code').textContent = JSON.stringify(JSON.parse(modelRes.output), null, 2);
    } catch {
      document.getElementById('log-output-code').textContent = modelRes.output;
    }
    document.getElementById('log-reasoning-text').textContent = modelRes.reasoning || "No reasoning logged.";
  }
  
  renderBoardGrid();
  setTimelineStep(0);
}

function renderBoardGrid() {
  const board = document.getElementById('game-board');
  if (!board || !activeTestCase) return;
  
  const game = activeTestCase.game;
  board.innerHTML = '';
  
  // Set dimensions dynamically
  board.style.gridTemplateColumns = `repeat(${game.width}, 1fr)`;
  board.style.gridTemplateRows = `repeat(${game.height}, 1fr)`;
  
  // Compute cell sizes based on grid width
  const maxGridWidth = Math.min(500, game.width * 75);
  board.style.width = `${maxGridWidth}px`;
  
  // Make portals mapping
  const portalsMap = {};
  if (game.portals) {
    game.portals.forEach((pair, idx) => {
      portalsMap[pair[0]] = { pair: pair[1], color: getPortalColor(idx), idx: idx+1 };
      portalsMap[pair[1]] = { pair: pair[0], color: getPortalColor(idx), idx: idx+1 };
    });
  }

  // Generate cells
  const totalCells = game.width * game.height;
  for (let s = 1; s <= totalCells; s++) {
    const cell = document.createElement('div');
    cell.className = 'board-cell';
    cell.dataset.space = s;
    
    // Add grid positions for line calculation later
    const x = (s - 1) % game.width;
    const y = Math.floor((s - 1) / game.width);
    
    cell.innerHTML = `
      <span class="cell-number">${s}</span>
      <span class="cell-coords">(${y+1},${x+1})</span>
    `;
    
    // Start / Goal Space highlights
    if (s === game.start) {
      cell.classList.add('cell-start');
    } else if (s === game.goal) {
      cell.classList.add('cell-goal');
    }
    
    // Blocked spaces highlight
    if (game.blocked && game.blocked.includes(s)) {
      cell.classList.add('cell-blocked');
    }
    
    // Portals highlight
    if (portalsMap[s]) {
      cell.classList.add('cell-portal');
      const portalPulse = document.createElement('div');
      portalPulse.className = 'portal-pulse';
      portalPulse.style.background = `radial-gradient(circle, ${portalsMap[s].color}, #080b11)`;
      portalPulse.style.boxShadow = `0 0 8px ${portalsMap[s].color}`;
      portalPulse.textContent = `P${portalsMap[s].idx}`;
      portalPulse.title = `Teleport to Space ${portalsMap[s].pair}`;
      cell.appendChild(portalPulse);
    }
    
    board.appendChild(cell);
  }
  
  // Append SVG overlay container for path drawing
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('class', 'board-svg-overlay');
  svg.setAttribute('id', 'board-path-svg');
  board.appendChild(svg);
  
  // Add Player Token dynamically inside the board
  const player = document.createElement('div');
  player.className = 'player-token';
  player.id = 'player-token';
  player.innerHTML = '<i class="fa-solid fa-person-running"></i>';
  board.appendChild(player);
}

// Find absolute coordinate centers of spaces relative to grid container
function getSpaceCenter(space) {
  const cell = document.querySelector(`.board-cell[data-space="${space}"]`);
  const board = document.getElementById('game-board');
  if (!cell || !board) return null;
  
  const cellRect = cell.getBoundingClientRect();
  const boardRect = board.getBoundingClientRect();
  
  return {
    x: cellRect.left - boardRect.left + cellRect.width / 2,
    y: cellRect.top - boardRect.top + cellRect.height / 2
  };
}

// Draw paths connecting cells in SVG
function drawPaths() {
  const svg = document.getElementById('board-path-svg');
  if (!svg || !activeTestCase) return;
  
  // Clear SVG
  svg.innerHTML = '';
  
  const game = activeTestCase.game;
  const modelRes = activeTestCase.results[activeModel];
  
  // 1. Draw Expected (Optimal) Path in Green
  if (activeTestCase.answer && activeTestCase.answer.path) {
    const expectedPoints = [game.start];
    activeTestCase.answer.path.forEach(step => {
      expectedPoints.push(step.final_space);
    });
    
    const dStr = buildPathDString(expectedPoints);
    if (dStr) {
      const pathEl = document.createElementNS('http://www.w3.org/2000/svg', 'path');
      pathEl.setAttribute('d', dStr);
      pathEl.setAttribute('class', 'path-line-expected');
      svg.appendChild(pathEl);
    }
  }
  
  // 2. Draw Model Path in Purple (up to current timeline step)
  if (modelRes && modelRes.replay_path) {
    const modelPoints = [game.start];
    // We only draw the path up to the active step so it animatedly grows!
    const activePath = modelRes.replay_path.slice(0, activeTimelineStep);
    activePath.forEach(step => {
      // Connect to chosen landing, then final space to visualize portals/wind bend
      if (step.chosen_landing !== step.final_space) {
        modelPoints.push(step.chosen_landing);
      }
      modelPoints.push(step.final_space);
    });
    
    const dStr = buildPathDString(modelPoints);
    if (dStr) {
      const pathEl = document.createElementNS('http://www.w3.org/2000/svg', 'path');
      pathEl.setAttribute('d', dStr);
      pathEl.setAttribute('class', 'path-line-model');
      svg.appendChild(pathEl);
      
      // Draw small arrowhead marker or circle at landing points
      modelPoints.forEach((sp, idx) => {
        if (idx === 0) return; // skip start
        const center = getSpaceCenter(sp);
        if (center) {
          const circle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
          circle.setAttribute('cx', center.x);
          circle.setAttribute('cy', center.y);
          circle.setAttribute('r', '3');
          circle.setAttribute('fill', idx === modelPoints.length - 1 ? 'white' : 'var(--primary)');
          circle.setAttribute('stroke', 'var(--bg-base)');
          circle.setAttribute('stroke-width', '1');
          svg.appendChild(circle);
        }
      });
    }
  }
}

function buildPathDString(points) {
  let d = '';
  let validPointsCount = 0;
  
  points.forEach((space, idx) => {
    const center = getSpaceCenter(space);
    if (center) {
      if (validPointsCount === 0) {
        d += `M ${center.x} ${center.y}`;
      } else {
        d += ` L ${center.x} ${center.y}`;
      }
      validPointsCount++;
    }
  });
  
  return validPointsCount > 1 ? d : null;
}

// Update Replay state and Position Token
function setTimelineStep(stepIdx) {
  activeTimelineStep = stepIdx;
  
  const timeline = document.getElementById('step-timeline');
  timeline.value = stepIdx;
  
  const modelRes = activeTestCase.results[activeModel];
  const totalSteps = modelRes ? modelRes.replay_path.length : 0;
  
  document.getElementById('current-step-label').textContent = `Step ${stepIdx} / ${totalSteps}`;
  
  // Highlight cells on board that belong to current trajectory
  document.querySelectorAll('.board-cell').forEach(cell => {
    cell.style.boxShadow = '';
    cell.style.background = '';
  });
  
  // Move Player Token
  let currentSpace = activeTestCase.game.start;
  const explanation = document.getElementById('step-explanation-content');
  
  if (stepIdx === 0) {
    explanation.innerHTML = `
      <div class="step-details-grid">
        <div class="step-detail-item"><span class="lbl">Turn:</span><span class="val">0 (Start)</span></div>
        <div class="step-detail-item"><span class="lbl">Position:</span><span class="val">Space ${currentSpace}</span></div>
      </div>
      <p style="margin-top: 0.5rem; font-style: italic;">The game begins on turn 1. Choose your first move.</p>
    `;
  } else if (modelRes && modelRes.replay_path[stepIdx - 1]) {
    const step = modelRes.replay_path[stepIdx - 1];
    currentSpace = step.final_space;
    
    // Detail breakdown
    const isPortalTriggered = step.chosen_landing !== step.final_space && step.note && step.note.includes('portal');
    const isWindTriggered = step.note && step.note.includes('wind');
    
    let forcedHtml = '';
    if (isPortalTriggered) {
      forcedHtml += `
        <div class="portal-event">
          <i class="fa-solid fa-circle-nodes"></i>
          <span>Portal activated! Teleported to Space ${step.final_space}</span>
        </div>
      `;
    }
    if (isWindTriggered) {
      forcedHtml += `
        <div class="wind-event">
          <i class="fa-solid fa-wind"></i>
          <span>${step.note.split(';').find(n => n.includes('wind'))}</span>
        </div>
      `;
    }
    
    explanation.innerHTML = `
      <div class="step-details-grid">
        <div class="step-detail-item"><span class="lbl">Turn:</span><span class="val">${step.turn}</span></div>
        <div class="step-detail-item"><span class="lbl">Move Chosen:</span><span class="val" style="color: var(--primary); font-weight:700;">"${step.move}"</span></div>
        <div class="step-detail-item"><span class="lbl">From Space:</span><span class="val">${step.from_space}</span></div>
        <div class="step-detail-item"><span class="lbl">Landed On:</span><span class="val">${step.chosen_landing}</span></div>
        <div class="step-detail-item"><span class="lbl">Final Space:</span><span class="val" style="color: var(--success); font-weight:700;">Space ${step.final_space}</span></div>
        <div class="step-detail-item"><span class="lbl">Rule Cycle:</span><span class="val" style="font-size:0.75rem;">${step.rule}</span></div>
      </div>
      ${forcedHtml}
    `;
    
    // Highlight landing & final cells
    const landingCell = document.querySelector(`.board-cell[data-space="${step.chosen_landing}"]`);
    if (landingCell) {
      landingCell.style.boxShadow = 'inset 0 0 8px rgba(139, 92, 246, 0.4)';
    }
  }
  
  // Position the player token element at space center
  // Wrap in requestAnimationFrame to ensure the grid cells are rendered and positionable
  requestAnimationFrame(() => {
    const center = getSpaceCenter(currentSpace);
    const token = document.getElementById('player-token');
    if (center && token) {
      token.style.left = `${center.x}px`;
      token.style.top = `${center.y}px`;
      token.style.display = 'flex';
    }
    
    // Redraw SVG path lines
    drawPaths();
  });
}

// Playback Logic
function togglePlayback() {
  const btn = document.getElementById('btn-play-pause');
  const icon = btn.querySelector('i');
  
  if (playbackInterval) {
    stopPlayback();
  } else {
    // Play
    icon.className = 'fa-solid fa-pause';
    btn.classList.remove('btn-primary');
    btn.classList.add('btn-secondary');
    
    const modelRes = activeTestCase.results[activeModel];
    const totalSteps = modelRes ? modelRes.replay_path.length : 0;
    
    if (activeTimelineStep >= totalSteps) {
      // Loop back to start
      setTimelineStep(0);
    }
    
    playbackInterval = setInterval(stepForward, playbackSpeed);
  }
}

function stopPlayback() {
  if (playbackInterval) {
    clearInterval(playbackInterval);
    playbackInterval = null;
  }
  const btn = document.getElementById('btn-play-pause');
  const icon = btn.querySelector('i');
  icon.className = 'fa-solid fa-play';
  btn.classList.remove('btn-secondary');
  btn.classList.add('btn-primary');
}

function stepForward() {
  const modelRes = activeTestCase.results[activeModel];
  const totalSteps = modelRes ? modelRes.replay_path.length : 0;
  
  if (activeTimelineStep < totalSteps) {
    setTimelineStep(activeTimelineStep + 1);
  } else {
    stopPlayback();
  }
}

function stepBackward() {
  if (activeTimelineStep > 0) {
    setTimelineStep(activeTimelineStep - 1);
  }
}

// Utility Helpers
function _spaceToCoordText(space, width) {
  const zeroBased = space - 1;
  const x = zeroBased % width;
  const y = Math.floor(zeroBased / width);
  return `(row ${y + 1}, column ${x + 1})`;
}

function getPortalColor(index) {
  const colors = [
    '#e879f9', // pink/magenta
    '#38bdf8', // sky blue
    '#fb7185', // rose
    '#fbbf24'  // amber
  ];
  return colors[index % colors.length];
}
