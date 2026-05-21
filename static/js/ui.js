// Screen navigation, lobby controls, status bar, game-over overlay.

function showScreen(id) {
  document.querySelectorAll('.screen').forEach(el => el.classList.remove('active'));
  document.getElementById(id).classList.add('active');
}

function showTab(which) {
  document.getElementById('tab-create').classList.toggle('active', which === 'create');
  document.getElementById('tab-join').classList.toggle('active', which === 'join');
  document.getElementById('panel-create').classList.toggle('hidden', which !== 'create');
  document.getElementById('panel-join').classList.toggle('hidden', which !== 'join');
}

function selectMode(m) {
  state.mode = m;
  document.getElementById('mode-pvp').classList.toggle('active', m === 'pvp');
  document.getElementById('mode-ai').classList.toggle('active', m === 'ai');
  document.getElementById('difficulty-row').classList.toggle('hidden', m !== 'ai');
  document.getElementById('first-move-opp').textContent =
    (m === 'ai') ? 'AI goes first' : 'Opponent goes first';
  // Only show the relevant leaderboard card for the selected mode.
  document.getElementById('leaderboard-card').classList.toggle('hidden', m !== 'ai');
  document.getElementById('pvp-card').classList.toggle('hidden', m === 'ai');
}

function showError(msg) {
  const banner = document.getElementById('error-banner');
  banner.textContent = msg;
  banner.style.display = 'block';
  clearTimeout(showError._t);
  showError._t = setTimeout(() => { banner.style.display = 'none'; }, 4000);
}

function setStatus(text) {
  document.getElementById('status-bar').textContent = text;
}

function updatePlayerBars() {
  const g = state.game;
  if (!g) return;

  // Reserves
  const myReserve = g.reserve[state.yourPlayer];
  const oppReserve = g.reserve[1 - state.yourPlayer];
  document.getElementById('my-reserve').textContent = myReserve;
  document.getElementById('opp-reserve').textContent = oppReserve;

  // Names
  document.getElementById('my-name-text').textContent = state.myName + (state.mode === 'ai' ? '' : '');
  document.getElementById('opp-name-text').textContent = state.opponentName;

  // Turn highlight
  const myTurn = g.current_player === state.yourPlayer && !g.game_over;
  document.getElementById('my-bar').classList.toggle('turn', myTurn);
  document.getElementById('opp-bar').classList.toggle('turn', !myTurn && !g.game_over);

  // Records / scores
  const myWins = state.myScore || 0;
  const oppWins = state.oppScore || 0;
  document.getElementById('my-record').textContent = state.gamesPlayed ? `${myWins} W` : '';
  document.getElementById('opp-record').textContent = state.gamesPlayed ? `${oppWins} W` : '';
}

function updateStatus() {
  const g = state.game;
  if (!g) return;
  if (g.game_over) {
    if (g.winner === null) setStatus("Draw.");
    else if (g.winner === state.yourPlayer) setStatus("You WIN!");
    else setStatus("You lose.");
    showGameOver();
    return;
  }
  if (g.retrieve_open && g.current_player === state.yourPlayer) {
    setStatus(`Bonus retrieval — you may take ${2 - g.retrievals_taken.length} more.`);
    document.getElementById('retrieve-bar').classList.remove('hidden');
    return;
  }
  document.getElementById('retrieve-bar').classList.add('hidden');
  if (g.retrieve_open) {
    setStatus(`${state.opponentName} is retrieving...`);
    return;
  }
  if (g.current_player === state.yourPlayer) {
    setStatus(state.liftFrom
      ? "Choose a higher empty slot to lift to (or Cancel)."
      : "Your turn — click a slot to place, or click your own marble to lift.");
  } else {
    setStatus(`Waiting for ${state.opponentName}...`);
  }
}

function showGameOver() {
  const g = state.game;
  const box = document.getElementById('game-over-overlay');
  box.classList.add('show');
  const title = document.getElementById('game-over-title');
  const scores = document.getElementById('game-over-scores');
  if (g.winner === null) {
    title.textContent = "Draw";
  } else if (g.winner === state.yourPlayer) {
    title.textContent = "You WIN!";
  } else {
    title.textContent = "You lose";
  }
  scores.innerHTML = `
    <div>Reserve — you: <b>${g.reserve[state.yourPlayer]}</b>, opp: <b>${g.reserve[1 - state.yourPlayer]}</b></div>
    <div style="margin-top:6px">Series — you: <b>${state.myScore}</b>, opp: <b>${state.oppScore}</b> (${state.gamesPlayed} games)</div>
  `;
  const post = document.getElementById('post-lb-btn');
  post.style.display = (state.mode === 'ai') ? '' : 'none';
}

function hideGameOver() {
  document.getElementById('game-over-overlay').classList.remove('show');
}

function goToMainMenu() {
  if (state.socket) state.socket.disconnect();
  state.socket = null;
  state.roomId = null;
  state.game = null;
  state.liftFrom = null;
  hideGameOver();
  document.getElementById('chat-messages').innerHTML = '';
  document.getElementById('retrieve-bar').classList.add('hidden');
  showScreen('screen-lobby');
  loadLeaderboard();
  loadPvpRankings();
  initSocket();
}

function copyCode() {
  const code = document.getElementById('waiting-code').textContent;
  navigator.clipboard?.writeText(code);
}
