/* AI Assistant chat panel for the Protocol Runner. */

let chatVisible = false;

function toggleChat() {
  chatVisible = !chatVisible;
  const panel = document.getElementById("chat-panel");
  panel.style.display = chatVisible ? "flex" : "none";
  document.getElementById("btn-chat").classList.toggle("active", chatVisible);
}

function appendChatMessage(role, content) {
  const el = document.getElementById("chat-messages");
  const msg = document.createElement("div");
  msg.className = "chat-msg " + role;

  if (role === "assistant" && content.includes("async def run")) {
    // Code response — show with "Insert" button
    const pre = document.createElement("pre");
    pre.className = "chat-code";
    pre.textContent = content;
    msg.appendChild(pre);

    const actions = document.createElement("div");
    actions.className = "chat-actions";

    const insertBtn = document.createElement("button");
    insertBtn.textContent = "Insert into Editor";
    insertBtn.onclick = () => {
      if (editor) editor.setValue(content);
      appendConsole("Code inserted into editor", "info");
    };
    actions.appendChild(insertBtn);

    const runBtn = document.createElement("button");
    runBtn.textContent = "Insert & Run";
    runBtn.onclick = () => {
      if (editor) editor.setValue(content);
      runProtocol();
    };
    actions.appendChild(runBtn);

    msg.appendChild(actions);
  } else {
    msg.textContent = content;
  }

  el.appendChild(msg);
  el.scrollTop = el.scrollHeight;
}

async function sendChat() {
  const input = document.getElementById("chat-input");
  const message = input.value.trim();
  if (!message) return;

  input.value = "";
  input.disabled = true;
  appendChatMessage("user", message);
  appendChatMessage("assistant", "Thinking...");

  try {
    const resp = await fetch("/api/assistant/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: message }),
    });

    // Remove "Thinking..." placeholder
    const msgs = document.getElementById("chat-messages");
    msgs.removeChild(msgs.lastChild);

    if (!resp.ok) {
      const err = await resp.json();
      appendChatMessage("assistant", "Error: " + (err.detail || "Request failed"));
    } else {
      const data = await resp.json();
      appendChatMessage("assistant", data.code);
    }
  } catch (e) {
    const msgs = document.getElementById("chat-messages");
    msgs.removeChild(msgs.lastChild);
    appendChatMessage("assistant", "Error: " + e.message);
  } finally {
    input.disabled = false;
    input.focus();
  }
}

function clearChat() {
  document.getElementById("chat-messages").innerHTML = "";
  fetch("/api/assistant/clear", { method: "POST" });
}

// Enter to send
document.addEventListener("DOMContentLoaded", () => {
  const input = document.getElementById("chat-input");
  if (input) {
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        sendChat();
      }
    });
  }
});
