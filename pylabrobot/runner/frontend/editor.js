/* Monaco Editor integration for the Protocol Runner. */

let editor = null;
let currentProtocolName = null;
let isDirty = false;

async function initEditor() {
  require.config({
    paths: {
      vs: "https://cdn.jsdelivr.net/npm/monaco-editor@0.50.0/min/vs",
    },
  });

  require(["vs/editor/editor.main"], function () {
    editor = monaco.editor.create(document.getElementById("editor-container"), {
      value: "",
      language: "python",
      theme: "vs-dark",
      fontSize: 13,
      minimap: { enabled: false },
      automaticLayout: true,
      scrollBeyondLastLine: false,
      wordWrap: "on",
      tabSize: 2,
      insertSpaces: true,
      renderLineHighlight: "line",
      lineNumbers: "on",
      padding: { top: 8 },
    });

    editor.onDidChangeModelContent(() => {
      if (!isDirty) {
        isDirty = true;
        updateTitle();
      }
    });

    // Ctrl+S to save
    editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyS, () => {
      saveCurrentProtocol();
    });

    // Load starter template
    loadStarter();
  });
}

function updateTitle() {
  const el = document.getElementById("protocol-name");
  if (!el) return;
  const name = currentProtocolName || "untitled";
  el.textContent = name + (isDirty ? " *" : "");
}

async function loadStarter() {
  try {
    const resp = await fetch("/api/protocols/_starter");
    const data = await resp.json();
    if (editor && data.code) {
      editor.setValue(data.code);
      currentProtocolName = "untitled";
      isDirty = false;
      updateTitle();
    }
  } catch (e) {
    console.error("Failed to load starter:", e);
  }
}

async function saveCurrentProtocol() {
  if (!editor) return;
  let name = currentProtocolName || "untitled";

  if (name === "untitled") {
    name = prompt("Protocol name:", "my_protocol");
    if (!name) return;
  }

  try {
    const resp = await fetch(`/api/protocols/${name}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code: editor.getValue() }),
    });
    const data = await resp.json();
    if (data.saved) {
      currentProtocolName = name;
      isDirty = false;
      updateTitle();
      appendConsole(`Protocol '${name}' saved.`, "stdout");
      refreshProtocolList();
    }
  } catch (e) {
    appendConsole(`Save failed: ${e}`, "stderr");
  }
}

async function loadProtocol(name) {
  try {
    const resp = await fetch(`/api/protocols/${name}`);
    if (!resp.ok) throw new Error(`Not found: ${name}`);
    const data = await resp.json();
    if (editor && data.code) {
      editor.setValue(data.code);
      currentProtocolName = name;
      isDirty = false;
      updateTitle();
    }
  } catch (e) {
    appendConsole(`Load failed: ${e}`, "stderr");
  }
}

async function refreshProtocolList() {
  try {
    const resp = await fetch("/api/protocols");
    const data = await resp.json();
    const list = document.getElementById("protocol-list");
    if (!list) return;
    list.innerHTML = "";
    for (const name of data.protocols) {
      const btn = document.createElement("button");
      btn.className = "protocol-item";
      btn.textContent = name;
      btn.onclick = () => loadProtocol(name);
      list.appendChild(btn);
    }
  } catch (e) {
    console.error("Failed to refresh protocol list:", e);
  }
}

async function newProtocol() {
  await loadStarter();
}

// Initialize after DOM is ready
window.addEventListener("load", () => {
  initEditor();
  refreshProtocolList();
});
