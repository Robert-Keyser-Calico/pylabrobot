/* Channel state visualization for the Protocol Runner. */

function renderChannels(data) {
  const container = document.getElementById("channel-state");
  if (!container || !data || !data.channels) return;

  let html = '';
  const channels = data.channels;
  const n = channels.length;

  for (let i = 0; i < n; i++) {
    const ch = channels[i];
    const fillPct = ch.has_tip && ch.max_volume > 0
      ? Math.min(100, (ch.volume / ch.max_volume) * 100)
      : 0;

    const tipColor = ch.has_tip ? '#4ec9b0' : '#444';
    const fillColor = ch.volume > 0 ? '#3b82f6' : 'transparent';
    const volLabel = ch.has_tip ? ch.volume.toFixed(1) + ' uL' : '';
    const maxLabel = ch.has_tip ? ch.max_volume.toFixed(0) + ' uL max' : 'no tip';
    const tipType = ch.tip && ch.tip.tip_type ? ch.tip.tip_type : '';

    html += `
      <div class="channel-col" title="Ch ${i + 1}: ${ch.has_tip ? 'Tip mounted' : 'No tip'}${ch.has_tip ? '\\nVolume: ' + ch.volume.toFixed(1) + ' / ' + ch.max_volume.toFixed(0) + ' uL' : ''}${tipType ? '\\nType: ' + tipType : ''}">
        <div class="channel-label">Ch${i + 1}</div>
        <div class="channel-tube">
          <div class="channel-fill" style="height:${fillPct}%;background:${fillColor}"></div>
        </div>
        <div class="channel-tip" style="border-bottom-color:${tipColor}"></div>
        <div class="channel-vol">${volLabel}</div>
        <div class="channel-max">${maxLabel}</div>
      </div>`;
  }

  container.innerHTML = html;
}

// Listen for WebSocket channel_state events
function handleChannelState(data) {
  renderChannels(data);
}

// Initial fetch
async function fetchChannelState() {
  try {
    const resp = await fetch("/api/channels");
    const data = await resp.json();
    renderChannels(data);
  } catch (e) {
    // ignore — no device yet
  }
}
