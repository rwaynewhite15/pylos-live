// Lobby + in-game leaderboard panels.

let _lbDifficulty = 'all';

function filterLeaderboard(d) {
  _lbDifficulty = d;
  document.querySelectorAll('#lb-filter .toggle-btn').forEach(b => {
    b.classList.toggle('active', b.textContent.toLowerCase() === d
                      || (b.textContent.toLowerCase() === 'all' && d === 'all'));
  });
  loadLeaderboard();
}

function toggleAdminMode() {
  if (state.adminMode) {
    state.adminMode = false;
    state.adminPassword = null;
    _updateAdminButtons();
    loadLeaderboard();
    loadPvpRankings();
    return;
  }
  const pw = prompt('Admin password:');
  if (!pw) return;
  // Verify by hitting the check endpoint
  fetch('/admin/check', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ password: pw }),
  }).then(r => r.json()).then(j => {
    if (j.ok) {
      state.adminMode = true;
      state.adminPassword = pw;
      _updateAdminButtons();
      loadLeaderboard();
      loadPvpRankings();
    } else {
      showError('Wrong password');
    }
  }).catch(() => showError('Network error'));
}

function _updateAdminButtons() {
  document.querySelectorAll('.admin-toggle').forEach(b => {
    b.textContent = state.adminMode ? 'Exit Admin' : '🔒 Admin';
    b.classList.toggle('admin-active', !!state.adminMode);
  });
}

function _adminButtons(kind, idOrName) {
  if (!state.adminMode) return '';
  const editArg = JSON.stringify(idOrName);
  return `<button class="lb-edit" onclick="${kind}Edit(${editArg})" title="Edit">✎</button>` +
         `<button class="lb-del"  onclick="${kind}Delete(${editArg})" title="Delete">×</button>`;
}

function renderLeaderboard(rows, target) {
  if (!rows.length) {
    target.innerHTML = '<p class="muted center small">No scores yet — be the first!</p>';
    return;
  }
  let html = '<table class="lb"><thead><tr><th>#</th><th>Name</th><th>Diff</th><th class="num">W</th><th class="num">L</th><th></th></tr></thead><tbody>';
  rows.forEach((r, i) => {
    html += `<tr><td class="rank">${i+1}</td><td>${escapeHtml(r.name)}</td><td>${r.difficulty}</td><td class="num">${r.wins}</td><td class="num">${r.losses}</td><td class="admin-cell">${_adminButtons('lb', r.id)}</td></tr>`;
  });
  html += '</tbody></table>';
  target.innerHTML = html;
}

function loadLeaderboard() {
  const qs = (_lbDifficulty === 'all') ? '' : '?difficulty=' + _lbDifficulty;
  fetch('/leaderboard' + qs).then(r => r.json()).then(rows => {
    rows = rows || [];
    const lobby = document.getElementById('lb-body');
    if (lobby) renderLeaderboard(rows, lobby);
    const game = document.getElementById('game-lb-body');
    if (game) renderLeaderboard(rows, game);
  }).catch(() => {});
}

function lbDelete(id) {
  if (!confirm('Delete this leaderboard entry?')) return;
  fetch('/leaderboard/delete', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ id, password: state.adminPassword }),
  }).then(r => r.json()).then(j => {
    if (j.ok) loadLeaderboard();
    else showError(j.error || 'Delete failed');
  }).catch(() => showError('Network error'));
}

function lbEdit(id) {
  // Find the row in the rendered table to seed defaults.
  const trs = document.querySelectorAll('#lb-body tr, #game-lb-body tr');
  let cur = null;
  for (const tr of trs) {
    const btn = tr.querySelector(`button.lb-edit[onclick*="lbEdit(${id})"]`);
    if (btn) {
      const tds = tr.querySelectorAll('td');
      cur = { name: tds[1].textContent.trim(), difficulty: tds[2].textContent.trim(),
              wins: tds[3].textContent.trim(), losses: tds[4].textContent.trim() };
      break;
    }
  }
  cur = cur || { name: '', difficulty: 'hard', wins: '0', losses: '0' };
  const name = prompt('Name:', cur.name);
  if (name === null) return;
  const difficulty = prompt('Difficulty (easy|medium|hard):', cur.difficulty);
  if (difficulty === null) return;
  const wins = prompt('Wins:', cur.wins);
  if (wins === null) return;
  const losses = prompt('Losses:', cur.losses);
  if (losses === null) return;
  fetch('/leaderboard/edit', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
      id, password: state.adminPassword,
      name: name.trim(), difficulty: difficulty.trim().toLowerCase(),
      wins: parseInt(wins, 10), losses: parseInt(losses, 10),
    }),
  }).then(r => r.json()).then(j => {
    if (j.ok) loadLeaderboard();
    else showError(j.error || 'Edit failed');
  }).catch(() => showError('Network error'));
}

function submitScore() {
  if (state.mode !== 'ai') return;
  const wins = state.myScore || 0;
  const losses = state.oppScore || 0;
  if (wins + losses === 0) { showError('No games played yet'); return; }
  fetch('/submit_score', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
      name: state.myName, difficulty: state.difficulty,
      wins, losses,
    })
  }).then(r => r.json()).then(j => {
    if (j.ok) {
      state.seriesPosted = true;
      document.getElementById('post-lb-btn').style.display = 'none';
      loadLeaderboard();
    } else {
      showError(j.error || 'Submit failed');
    }
  }).catch(() => showError('Network error'));
}

// PvP rankings ────────────────────────────────────────────────────

function pvpTab(name) {
  ['rankings', 'history', 'lookup'].forEach(t => {
    document.getElementById('pvp-' + t + '-panel').classList.toggle('hidden', t !== name);
  });
  document.querySelectorAll('#pvp-tab-bar .toggle-btn').forEach(b => {
    b.classList.toggle('active', b.textContent.toLowerCase() === name);
  });
  if (name === 'rankings') loadPvpRankings();
  if (name === 'history') loadPvpHistory();
}

function loadPvpRankings() {
  fetch('/pvp/rankings').then(r => r.json()).then(rows => {
    const body = document.getElementById('pvp-rankings-body');
    if (!rows.length) { body.innerHTML = '<p class="muted center small">No ranked games yet.</p>'; return; }
    let html = '<table class="lb"><thead><tr><th>#</th><th>Name</th><th class="num">ELO</th><th class="num">W</th><th class="num">L</th><th></th></tr></thead><tbody>';
    rows.forEach((r, i) => {
      html += `<tr><td class="rank">${i+1}</td><td>${escapeHtml(r.name)}</td><td class="num">${r.elo}</td><td class="num">${r.wins}</td><td class="num">${r.losses}</td><td class="admin-cell">${_adminButtons('pvp', r.name)}</td></tr>`;
    });
    html += '</tbody></table>';
    body.innerHTML = html;
  }).catch(() => {});
}

function pvpDelete(name) {
  if (!confirm(`Remove "${name}" from PvP rankings? Their game history will also be deleted.`)) return;
  fetch('/pvp/player/delete', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ name, password: state.adminPassword }),
  }).then(r => r.json()).then(j => {
    if (j.ok) { loadPvpRankings(); loadPvpHistory(); }
    else showError(j.error || 'Delete failed');
  }).catch(() => showError('Network error'));
}

function pvpEdit(name) {
  // Seed from the displayed row.
  const trs = document.querySelectorAll('#pvp-rankings-body tr');
  let cur = null;
  for (const tr of trs) {
    const btn = tr.querySelector(`button.lb-edit[onclick*='pvpEdit("${name.replace(/"/g,'\\"')}")']`);
    if (btn) {
      const tds = tr.querySelectorAll('td');
      cur = { name: tds[1].textContent.trim(), elo: tds[2].textContent.trim(),
              wins: tds[3].textContent.trim(), losses: tds[4].textContent.trim() };
      break;
    }
  }
  cur = cur || { name, elo: '1000', wins: '0', losses: '0' };
  const newName = prompt('Display name:', cur.name);
  if (newName === null) return;
  const elo = prompt('ELO:', cur.elo);
  if (elo === null) return;
  const wins = prompt('Wins:', cur.wins);
  if (wins === null) return;
  const losses = prompt('Losses:', cur.losses);
  if (losses === null) return;
  fetch('/pvp/player/edit', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
      name, password: state.adminPassword,
      new_display_name: newName.trim(),
      elo: parseInt(elo, 10),
      wins: parseInt(wins, 10),
      losses: parseInt(losses, 10),
    }),
  }).then(r => r.json()).then(j => {
    if (j.ok) loadPvpRankings();
    else showError(j.error || 'Edit failed');
  }).catch(() => showError('Network error'));
}

function loadPvpHistory() {
  fetch('/pvp/history').then(r => r.json()).then(rows => {
    const body = document.getElementById('pvp-history-body');
    if (!rows.length) { body.innerHTML = '<p class="muted center small">No games yet.</p>'; return; }
    let html = '<table class="lb"><thead><tr><th>P1</th><th>P2</th><th>Winner</th><th class="num">P1 ELO</th><th class="num">P2 ELO</th></tr></thead><tbody>';
    rows.forEach(r => {
      const sign1 = r.p1_elo_change >= 0 ? '+' : '';
      const sign2 = r.p2_elo_change >= 0 ? '+' : '';
      const c1 = r.p1_elo_change >= 0 ? 'pos-elo' : 'neg-elo';
      const c2 = r.p2_elo_change >= 0 ? 'pos-elo' : 'neg-elo';
      html += `<tr>
        <td>${escapeHtml(r.p1)}</td>
        <td>${escapeHtml(r.p2)}</td>
        <td>${escapeHtml(r.winner || '—')}</td>
        <td class="num">${r.p1_elo} <span class="${c1}">(${sign1}${r.p1_elo_change})</span></td>
        <td class="num">${r.p2_elo} <span class="${c2}">(${sign2}${r.p2_elo_change})</span></td>
      </tr>`;
    });
    html += '</tbody></table>';
    body.innerHTML = html;
  }).catch(() => {});
}

function lookupPlayer() {
  const name = document.getElementById('pvp-lookup-input').value.trim();
  if (!name) return;
  fetch('/pvp/player/' + encodeURIComponent(name)).then(r => r.json()).then(j => {
    const body = document.getElementById('pvp-lookup-body');
    if (j.error) { body.innerHTML = `<p class="muted center small">${escapeHtml(j.error)}</p>`; return; }
    let html = `<div class="card" style="margin:0 0 12px;padding:14px">
      <h3 style="margin:0 0 8px">${escapeHtml(j.name)}</h3>
      <p class="muted small" style="margin:0">ELO ${j.elo} · ${j.wins}W ${j.losses}L (${j.games} games)</p>
    </div>`;
    if (j.history.length) {
      html += '<table class="lb"><thead><tr><th>vs</th><th>Result</th><th class="num">Δ ELO</th></tr></thead><tbody>';
      j.history.forEach(g => {
        const me = j.name;
        const opp = (g.p1 === me) ? g.p2 : g.p1;
        const my_change = (g.p1 === me) ? g.p1_elo_change : g.p2_elo_change;
        const res = (g.winner === me) ? 'Win' : 'Loss';
        const sign = my_change >= 0 ? '+' : '';
        const cls = my_change >= 0 ? 'pos-elo' : 'neg-elo';
        html += `<tr><td>${escapeHtml(opp)}</td><td>${res}</td><td class="num ${cls}">${sign}${my_change}</td></tr>`;
      });
      html += '</tbody></table>';
    }
    body.innerHTML = html;
  }).catch(() => {});
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c =>
    ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'})[c]);
}
