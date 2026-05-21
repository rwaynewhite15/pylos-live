// Client-side mutable state shared across modules.
const state = {
  // socket
  socket: null,
  roomId: null,
  yourPlayer: 0,
  mode: null,          // 'ai' | 'pvp'
  difficulty: null,    // 'easy' | 'medium' | 'hard'
  opponentName: 'Opponent',
  myName: 'Player',
  firstPlayer: 0,
  game: null,          // last received state from server
  stateSeq: 0,
  myScore: 0,
  oppScore: 0,
  gamesPlayed: 0,
  // local UI
  liftFrom: null,      // {lv,r,c} when user is mid-lift
  pending: false,      // submitted a move, waiting for server
};
