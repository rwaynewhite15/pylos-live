// Ping the server every 10 minutes so Render's free tier doesn't spin the
// dyno down mid-game (free dynos sleep after ~15 minutes of no HTTP traffic).
let _keepAliveTimer = null;
function _startKeepAlive() {
  if (_keepAliveTimer) return;
  _keepAliveTimer = setInterval(() => fetch('/ping').catch(() => {}), 10 * 60 * 1000);
}

function initSocket() {
  if (state.socket) { try { state.socket.disconnect(); } catch(_){} }
  state.socket = io({ transports: ['websocket', 'polling'] });
  registerSocketEvents();
  _startKeepAlive();
}

function createRoom() {
  const name = (document.getElementById('name-input').value || '').trim() || 'Player';
  state.myName = name;
  const fp = document.getElementById('first-move-select').value;
  const difficulty = document.getElementById('difficulty-select').value;
  const mode = state.mode || 'pvp';
  state.mode = mode;
  state.difficulty = (mode === 'ai') ? difficulty : null;
  if (!state.socket) initSocket();
  state.socket.emit('create_room', {
    mode, difficulty, name, first_player: fp,
  });
}

function joinRoom() {
  const name = (document.getElementById('name-input').value || '').trim() || 'Player';
  const room = (document.getElementById('room-code-input').value || '').trim().toUpperCase();
  if (room.length < 4) { showError('Room code is required'); return; }
  state.myName = name;
  state.mode = 'pvp';
  if (!state.socket) initSocket();
  state.socket.emit('join_room_request', { room_id: room, name });
}

function requestRematch() {
  if (state.socket) state.socket.emit('rematch');
  hideGameOver();
}

function sendPlace(lv, r, c) {
  if (!state.socket) return;
  state.pending = true;
  state.socket.emit('move', { type: 'place', to: [lv, r, c] });
}

function sendLift(fl, fr, fc, tl, tr, tc) {
  if (!state.socket) return;
  state.pending = true;
  state.socket.emit('move', { type: 'lift', from: [fl, fr, fc], to: [tl, tr, tc] });
}

function sendRetrieve(lv, r, c) {
  if (!state.socket) return;
  state.socket.emit('retrieve', { at: [lv, r, c] });
}

function skipRetrieve() {
  if (!state.socket) return;
  state.socket.emit('skip_retrieve');
}
