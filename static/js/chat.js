function sendChat() {
  const input = document.getElementById('chat-input');
  const text = input.value.trim();
  if (!text || !state.socket) return;
  state.socket.emit('chat', { text });
  input.value = '';
}

function addChatMessage(data) {
  const box = document.getElementById('chat-messages');
  const div = document.createElement('div');
  div.className = 'chat-msg' + (data.from === state.yourPlayer ? ' me' : '');
  const from = document.createElement('span');
  from.className = 'from';
  from.textContent = data.name + ': ';
  div.appendChild(from);
  div.appendChild(document.createTextNode(data.text));
  box.appendChild(div);
  box.scrollTop = box.scrollHeight;
}
