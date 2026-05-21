// Bootstrap.

document.addEventListener('DOMContentLoaded', () => {
  // Default mode
  selectMode('pvp');
  showTab('create');

  // Chat
  document.getElementById('chat-send').addEventListener('click', sendChat);
  document.getElementById('chat-input').addEventListener('keydown', e => {
    if (e.key === 'Enter') sendChat();
  });

  // Lobby data
  loadLeaderboard();
  loadPvpRankings();

  initSocket();
});
