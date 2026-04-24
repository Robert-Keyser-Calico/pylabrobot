/* Arm position display for the Protocol Runner. */

function renderArms(data) {
  const container = document.getElementById("arm-state");
  if (!container || !data || !data.arms) return;

  if (data.arms.length === 0) {
    container.innerHTML = '<span class="arm-empty">No arms configured</span>';
    return;
  }

  let html = '';
  for (const arm of data.arms) {
    const pos = arm.position || { x: 0, y: 0, z: 0 };
    const rot = arm.rotation || { x: 0, y: 0, z: 0 };
    const hasRotation = rot.x !== 0 || rot.y !== 0 || rot.z !== 0;

    html += `<div class="arm-row">`;
    html += `<span class="arm-name">${arm.name}</span>`;
    html += `<span class="arm-coord">X:<b>${pos.x.toFixed(1)}</b></span>`;
    html += `<span class="arm-coord">Y:<b>${pos.y.toFixed(1)}</b></span>`;
    html += `<span class="arm-coord">Z:<b>${pos.z.toFixed(1)}</b></span>`;

    if (hasRotation) {
      html += `<span class="arm-coord">R:<b>${rot.z.toFixed(1)}°</b></span>`;
    }

    if (arm.holding) {
      html += `<span class="arm-holding">holding: ${arm.held_resource || '?'}</span>`;
    }

    if (arm.gripper_closed !== undefined) {
      html += `<span class="arm-gripper">${arm.gripper_closed ? 'grip' : 'open'}</span>`;
    }

    html += `</div>`;
  }

  container.innerHTML = html;
}

function handleArmState(data) {
  renderArms(data);
}

async function fetchArmState() {
  try {
    const resp = await fetch("/api/arms");
    const data = await resp.json();
    renderArms(data);
  } catch (e) {
    // ignore
  }
}
