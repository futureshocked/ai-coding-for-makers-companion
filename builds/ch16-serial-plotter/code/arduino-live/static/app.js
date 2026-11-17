/**
 * @fileoverview Frontend application for Arduino Sensor Visualiser.
 *
 * Connects to the Flask SSE backend (/stream) to receive live sensor readings,
 * renders them on a Chart.js multi-axis line chart, and provides controls for:
 *   - Pause/resume chart updates
 *   - Chart window selection (30s, 5m, all)
 *   - Sensor visibility toggles (temperature, humidity, lux)
 *   - Live stat cards (current, min, max, mean)
 *   - Log replay (/stream/replay) with configurable speed
 *   - Mode switching between live streaming and log replay
 *
 * Architecture: IIFE to avoid global namespace pollution. Single Chart.js
 * instance with three datasets on separate Y axes. SSE connections are
 * managed per-mode (live SSE vs replay SSE).
 *
 * @requires Chart.js 4.x (loaded via CDN in index.html)
 */
(function () {
    'use strict';

    // ── State ──────────────────────────────────────────────────────────
    let paused = false;
    let maxPoints = 30; // 30s default; 0 = unlimited
    let mode = 'live'; // 'live' or 'replay'
    let replaySource = null; // EventSource for replay
    let liveSource = null; // EventSource for live
    let replayAbort = null; // AbortController for fetch-based replay

    const data = {
        labels: [],
        temperature: [],
        humidity: [],
        lux: []
    };

    const stats = {
        temperature: { count: 0, sum: 0, min: Infinity, max: -Infinity },
        humidity:  { count: 0, sum: 0, min: Infinity, max: -Infinity },
        lux:       { count: 0, sum: 0, min: Infinity, max: -Infinity }
    };

    // ── DOM refs ───────────────────────────────────────────────────────
    const ctx = document.getElementById('liveChart').getContext('2d');
    const pauseBtn = document.getElementById('pauseBtn');
    const windowSelect = document.getElementById('window-select');
    const logSelect = document.getElementById('log-select');
    const replayBtn = document.getElementById('replay-btn');
    const liveBtn = document.getElementById('live-btn');
    const replaySpeed = document.getElementById('replay-speed');
    const toggles = {
        temperature: document.getElementById('toggle-temperature'),
        humidity:    document.getElementById('toggle-humidity'),
        lux:         document.getElementById('toggle-lux')
    };

    // ── Chart init ─────────────────────────────────────────────────────
    const chart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: data.labels,
            datasets: [
                {
                    label: 'Temperature (°C)',
                    data: data.temperature,
                    borderColor: '#ff6384',
                    backgroundColor: '#ff6384',
                    borderWidth: 2,
                    pointRadius: 0,
                    fill: false,
                    yAxisID: 'yTemp',
                    tension: 0.4,
                    cubicInterpolationMode: 'monotone'
                },
                {
                    label: 'Humidity (%)',
                    data: data.humidity,
                    borderColor: '#36a2eb',
                    backgroundColor: '#36a2eb',
                    borderWidth: 2,
                    pointRadius: 0,
                    fill: false,
                    yAxisID: 'yHumidity',
                    tension: 0.4,
                    cubicInterpolationMode: 'monotone'
                },
                {
                    label: 'Lux',
                    data: data.lux,
                    borderColor: '#ffce56',
                    backgroundColor: '#ffce56',
                    borderWidth: 2,
                    pointRadius: 0,
                    fill: false,
                    yAxisID: 'yLux',
                    tension: 0.4,
                    cubicInterpolationMode: 'monotone'
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            animation: false,
            interaction: {
                mode: 'index',
                intersect: false
            },
            plugins: {
                legend: {
                    display: true,
                    labels: { color: '#e0e0e0' }
                },
                tooltip: {
                    enabled: true
                }
            },
            scales: {
                x: {
                    ticks: {
                        color: '#a0a0a0',
                        maxTicksLimit: 10,
                        maxRotation: 0
                    },
                    grid: { color: 'rgba(255,255,255,0.05)' }
                },
                yTemp: {
                    type: 'linear',
                    display: true,
                    position: 'left',
                    title: { display: true, text: 'Temperature (°C)', color: '#ff6384' },
                    ticks: { color: '#ff6384' },
                    grid: { color: 'rgba(255,99,132,0.15)' }
                },
                yHumidity: {
                    type: 'linear',
                    display: true,
                    position: 'right',
                    title: { display: true, text: 'Humidity (%)', color: '#36a2eb' },
                    ticks: { color: '#36a2eb' },
                    grid: { drawOnChartArea: false }
                },
                yLux: {
                    type: 'linear',
                    display: true,
                    position: 'right',
                    title: { display: true, text: 'Lux', color: '#ffce56' },
                    ticks: { color: '#ffce56' },
                    grid: { drawOnChartArea: false }
                }
            }
        }
    });

    // ── Helpers ────────────────────────────────────────────────────────
    function formatTime(timestampMs) {
        const d = new Date(timestampMs);
        return d.toLocaleTimeString('en-GB'); // HH:MM:SS
    }

    function trimData() {
        if (maxPoints > 0 && data.labels.length > maxPoints) {
            const overflow = data.labels.length - maxPoints;
            data.labels.splice(0, overflow);
            data.temperature.splice(0, overflow);
            data.humidity.splice(0, overflow);
            data.lux.splice(0, overflow);
        }
    }

    function updateStatsEl(channel) {
        const card = document.getElementById('stat-' + channel);
        const s = stats[channel];
        if (s.count === 0) return;
        card.querySelector('.val-current').textContent = s.lastValue.toFixed(2);
        card.querySelector('.val-min').textContent     = s.min.toFixed(2);
        card.querySelector('.val-max').textContent     = s.max.toFixed(2);
        card.querySelector('.val-mean').textContent    = (s.sum / s.count).toFixed(2);
    }

    function resetStats() {
        ['temperature', 'humidity', 'lux'].forEach(function (ch) {
            stats[ch] = { count: 0, sum: 0, min: Infinity, max: -Infinity };
            const card = document.getElementById('stat-' + ch);
            card.querySelector('.val-current').textContent = '—';
            card.querySelector('.val-min').textContent     = '—';
            card.querySelector('.val-max').textContent     = '—';
            card.querySelector('.val-mean').textContent    = '—';
        });
    }

    function clearChartData() {
        data.labels.length = 0;
        data.temperature.length = 0;
        data.humidity.length = 0;
        data.lux.length = 0;
        chart.update();
    }

    function setMode(newMode) {
        mode = newMode;
        replayBtn.disabled = (mode === 'replay');
        liveBtn.disabled = (mode === 'live');
        replayBtn.classList.toggle('active', mode === 'replay');
        liveBtn.classList.toggle('active', mode === 'live');
    }

    // ── Process a single reading (shared by live and replay) ───────────
    function processReading(reading) {
        const timestampMs = reading.timestamp_ms;
        const timeLabel = formatTime(timestampMs);

        // ── Update stats ───────────────────────────────────────
        ['temperature', 'humidity', 'lux'].forEach(function (ch) {
            const key = ch === 'temperature' ? 'temperature_c'
                    : ch === 'humidity'    ? 'humidity_pct'
                    : 'lux';
            const val = reading[key];
            if (val === undefined || val === null) return;

            const s = stats[ch];
            s.count++;
            s.sum += val;
            s.min = Math.min(s.min, val);
            s.max = Math.max(s.max, val);
            s.lastValue = val;
            updateStatsEl(ch);
        });

        // ── Chart update (skip if paused) ────────────────────────
        if (paused) return;

        data.labels.push(timeLabel);
        data.temperature.push(reading.temperature_c);
        data.humidity.push(reading.humidity_pct);
        data.lux.push(reading.lux);

        trimData();
        chart.update();
    }

    // ── Live SSE connection ────────────────────────────────────────────
    function connectLive() {
        if (liveSource) {
            liveSource.close();
        }
        liveSource = new EventSource('/stream');

        liveSource.addEventListener('message', function (e) {
            let reading;
            try {
                reading = JSON.parse(e.data);
            } catch (err) {
                console.error('Invalid JSON:', e.data, err);
                return;
            }
            processReading(reading);
        });

        liveSource.onerror = function (err) {
            console.error('EventSource error:', err);
        };
    }

    // ── Replay via SSE ─────────────────────────────────────────────────
    function startReplay(filename, speed) {
        // Close live connection
        if (liveSource) {
            liveSource.close();
            liveSource = null;
        }

        // Reset state
        resetStats();
        clearChartData();
        setMode('replay');

        const url = '/stream/replay?filename=' + encodeURIComponent(filename) + '&speed=' + speed;
        replaySource = new EventSource(url);

        replaySource.addEventListener('message', function (e) {
            let reading;
            try {
                reading = JSON.parse(e.data);
            } catch (err) {
                console.error('Invalid JSON during replay:', e.data, err);
                return;
            }
            if (reading.error) {
                console.error('Replay error:', reading.error);
                stopReplay();
                return;
            }
            processReading(reading);
        });

        replaySource.addEventListener('error', function (e) {
            console.log('Replay stream ended or error occurred');
            stopReplay();
        });
    }

    function stopReplay() {
        if (replaySource) {
            replaySource.close();
            replaySource = null;
        }
        setMode('live');
    }

    // ── Load log list ──────────────────────────────────────────────────
    function loadLogList() {
        fetch('/api/logs')
            .then(function (resp) { return resp.json(); })
            .then(function (logs) {
                logSelect.innerHTML = '';
                if (logs.length === 0) {
                    var opt = document.createElement('option');
                    opt.value = '';
                    opt.textContent = 'No logs available';
                    logSelect.appendChild(opt);
                    return;
                }
                logs.forEach(function (log) {
                    var opt = document.createElement('option');
                    opt.value = log.filename;
                    opt.textContent = log.label;
                    logSelect.appendChild(opt);
                });
            })
            .catch(function (err) {
                console.error('Failed to load logs:', err);
                logSelect.innerHTML = '<option value="">Error loading logs</option>';
            });
    }

    // ── Controls ───────────────────────────────────────────────────────
    pauseBtn.addEventListener('click', function () {
        paused = !paused;
        pauseBtn.textContent = paused ? 'Resume' : 'Pause';
    });

    toggles.temperature.addEventListener('change', function () {
        chart.data.datasets[0].hidden = !this.checked;
        chart.update();
    });
    toggles.humidity.addEventListener('change', function () {
        chart.data.datasets[1].hidden = !this.checked;
        chart.update();
    });
    toggles.lux.addEventListener('change', function () {
        chart.data.datasets[2].hidden = !this.checked;
        chart.update();
    });

    windowSelect.addEventListener('change', function () {
        maxPoints = parseInt(this.value, 10);
        trimData();
        chart.update();
    });

    replayBtn.addEventListener('click', function () {
        var filename = logSelect.value;
        if (!filename) {
            alert('Please select a log file first.');
            return;
        }
        var speed = parseFloat(replaySpeed.value) || 1;
        startReplay(filename, speed);
    });

    liveBtn.addEventListener('click', function () {
        stopReplay();
        resetStats();
        clearChartData();
        connectLive();
    });

    // ── Resize handling ────────────────────────────────────────────────
    window.addEventListener('resize', function () {
        chart.resize();
    });

    // ── Init ───────────────────────────────────────────────────────────
    loadLogList();
    connectLive();
    setMode('live');
})();