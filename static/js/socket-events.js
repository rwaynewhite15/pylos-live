function registerSocketEvents() {
  const s = state.socket;
  if (!s) return;

  s.on('connect', () => { /* hooked */ });

  s.on('error', (data) => { showError(data.message || 'Error'); state.pending = false; });

  s.on('joined', (data) => {
    state.roomId = data.room_id;
    state.yourPlayer = data.player_id;
    state.mode = data.mode;
    state.firstPlayer = data.first_player ?? 0;
    if (data.difficulty) state.difficulty = data.difficulty;
    if (data.opponent) state.opponentName = data.opponent;
    document.getElementById('gh-mode').textContent =
      state.mode === 'ai' ? `vs AI (${state.difficulty})` : 'vs Player';
    document.getElementById('gh-room').textContent = state.roomId ? `Room: ${state.roomId}` : '';
    if (data.mode === 'pvp' && !data.opponent) {
      // creator, still waiting
    } else {
      showScreen('screen-game');
      window.boardReady?.(); // (re)build 3D scene
      loadLeaderboard();
    }
  });

  s.on('waiting', (data) => {
    document.getElementById('waiting-code').textContent = data.room_id;
    showScreen('screen-waiting');
  });

  s.on('state', (data) => {
    if (data.state_seq && data.state_seq < state.stateSeq) return;
    state.stateSeq = data.state_seq || 0;
    state.game = data;
    state.pending = false;
    state.myScore = data.scores?.[state.yourPlayer] ?? 0;
    state.oppScore = data.scores?.[1 - state.yourPlayer] ?? 0;
    state.gamesPlayed = data.games_played || 0;
    updatePlayerBars();
    updateStatus();
    window.boardRender?.();
    // Hide the thinking bar once the AI's state arrives.
    if (data.current_player === state.yourPlayer || data.game_over) {
      hideAiThinking();
    }
  });

  s.on('ai_progress', (data) => {
    showAiThinking(data);
  });

  s.on('new_game', (data) => {
    hideGameOver();
    state.liftFrom = null;
    state.firstPlayer = data.first_player ?? 0;
  });

  s.on('chat', (data) => { addChatMessage(data); });

  s.on('opponent_left', (data) => {
    showError(data.message || 'Opponent left.');
    setTimeout(goToMainMenu, 1500);
  });
}
