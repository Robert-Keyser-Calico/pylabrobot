/* PyLabRobot Runner — WebSocket client and event dispatch.
 *
 * Connects to the FastAPI /ws endpoint and dispatches events to the
 * Konva.js rendering layer (lib.js).
 */

let webSocket = null;

const statusLabel = document.getElementById("status-label");
const statusIndicator = document.getElementById("status-indicator");

function updateStatusLabel(status) {
  if (status === "loaded") {
    statusLabel.innerText = "Connected";
    statusLabel.className = "status-text connected";
    statusIndicator.className = "status-dot connected";
  } else if (status === "disconnected") {
    statusLabel.innerText = "Disconnected";
    statusLabel.className = "status-text disconnected";
    statusIndicator.className = "status-dot disconnected";
  } else {
    statusLabel.innerText = "Connecting...";
    statusLabel.className = "status-text";
    statusIndicator.className = "status-dot";
  }
}

// ============== Resource tree event handlers ==============

function setRootResource(data) {
  resource = loadResource(data.resource);
  resource.location = { x: 0, y: 0, z: 0 };
  resource.draw(resourceLayer);
  rootResource = resource;
  fitToViewport();
}

function removeResource(resourceName) {
  let resource = resources[resourceName];
  if (resource) resource.destroy();
}

function setState(allStates) {
  for (let resourceName in allStates) {
    let state = allStates[resourceName];
    let resource = resources[resourceName];
    if (!resource) continue;
    try {
      resource.setState(state);
    } catch (e) {
      console.error(`[setState] error for ${resourceName}:`, e);
    }
  }
}

async function processCentralEvent(event, data) {
  switch (event) {
    case "set_root_resource":
      setRootResource(data);
      break;

    case "resource_assigned":
      resource = loadResource(data.resource);
      resource.draw(resourceLayer);
      setState(data.state);
      break;

    case "resource_unassigned":
      removeResource(data.resource_name);
      break;

    case "set_state":
      setState(data);
      break;

    case "console_output":
      appendConsole(data.text, data.stream || "stdout");
      break;

    case "channel_state":
      if (typeof handleChannelState === 'function') handleChannelState(data);
      break;

    case "arm_state":
      if (typeof handleArmState === 'function') handleArmState(data);
      break;

    case "execution_started":
    case "execution_completed":
    case "execution_error":
    case "execution_stopped":
      break;

    default:
      console.warn(`Unknown event: ${event}`);
  }
}

async function handleEvent(id, event, data) {
  if (event === "ready" || event === "pong") return;

  const ret = { event: event, id: id };
  try {
    await processCentralEvent(event, data);
    ret.success = true;
  } catch (e) {
    console.error(e);
    ret.error = e.message;
    ret.success = false;
  }
  if (webSocket && webSocket.readyState === WebSocket.OPEN) {
    webSocket.send(JSON.stringify(ret));
  }
}

// ============== Console ==============

function appendConsole(text, stream) {
  const el = document.getElementById("console-output");
  if (!el) return;
  const line = document.createElement("div");
  line.className = "console-line " + (stream === "stderr" ? "stderr" : "stdout");
  line.textContent = text;
  el.appendChild(line);
  el.scrollTop = el.scrollHeight;
}

// ============== WebSocket connection ==============

function connectWebSocket() {
  updateStatusLabel("loading");
  const wsUrl = `ws://${window.location.host}/ws`;
  console.log("[runner] Connecting to WebSocket:", wsUrl);
  webSocket = new WebSocket(wsUrl);

  webSocket.onopen = function () {
    console.log("[runner] WebSocket connected to " + wsUrl);
    webSocket.send(JSON.stringify({ event: "ready" }));
    updateStatusLabel("loaded");
    const runBtn = document.getElementById("btn-run");
    if (runBtn) runBtn.disabled = false;
    if (typeof fetchChannelState === 'function') fetchChannelState();
    if (typeof fetchArmState === 'function') fetchArmState();
  };

  webSocket.onerror = function (err) {
    console.error("[runner] WebSocket error:", err);
    updateStatusLabel("disconnected");
  };

  webSocket.onclose = function () {
    updateStatusLabel("disconnected");
    setTimeout(connectWebSocket, 3000);
  };

  webSocket.addEventListener("message", function (event) {
    var data = JSON.parse(event.data, (key, value) => {
      if (value === "Infinity") return Infinity;
      if (value === "-Infinity") return -Infinity;
      return value;
    });
    handleEvent(data.id, data.event, data.data);
  });
}

// Connect after lib.js initializes the Konva stage on window.load
window.addEventListener("load", function () {
  console.log("[runner] window.load fired, stage:", !!stage);
  setTimeout(function() {
    console.log("[runner] Delayed connect, stage:", !!stage);
    connectWebSocket();
  }, 500);
});
