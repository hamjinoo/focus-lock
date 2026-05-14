const $ = (sel) => document.querySelector(sel);

async function refresh() {
  const { lastStatus, lastError } = await chrome.storage.local.get([
    "lastStatus",
    "lastError",
  ]);
  const el = $("#status");
  const rules = $("#rules");
  const err = $("#error");
  const hint = $("#incognito-hint");

  if (!lastStatus) {
    el.className = "status stale";
    el.textContent = "service not reached yet";
  } else {
    const { status, ruleCount } = lastStatus;
    const ageSec = Math.round((Date.now() - lastStatus.at) / 1000);
    const stale = ageSec > 30;
    if (stale) {
      el.className = "status stale";
      el.textContent = `service unreachable (${ageSec}s ago) — rules held`;
    } else if (status.frozen) {
      el.className = "status frozen";
      el.textContent = "FROZEN · " + ruleCount + " rules";
    } else if (status.active) {
      el.className = "status active";
      el.textContent = status.reason + " · " + ruleCount + " rules";
    } else {
      el.className = "status idle";
      el.textContent = "idle";
    }
    rules.textContent = ruleCount === 0
      ? "no domains being blocked at the browser layer"
      : `blocking: ${(status.blocked_domains || []).slice(0, 4).join(", ")}${status.blocked_domains.length > 4 ? " …" : ""}`;
  }

  if (lastError && lastError.message) {
    err.hidden = false;
    err.textContent = "last fetch error: " + lastError.message;
  } else {
    err.hidden = true;
  }

  // Incognito guidance
  if (chrome.extension.isAllowedIncognitoAccess) {
    const allowed = await chrome.extension.isAllowedIncognitoAccess();
    if (!allowed) {
      hint.hidden = false;
      hint.innerHTML =
        '시크릿 모드는 따로 허용해야 차단됩니다.<br>' +
        'chrome://extensions → focus-lock → "시크릿 모드에서 허용" ON';
    }
  }
}

refresh();
setInterval(refresh, 2000);
