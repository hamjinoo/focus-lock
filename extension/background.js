// focus-lock browser extension — service worker.
//
// Polls the local service every 5 seconds. When the service reports an
// active block, install declarativeNetRequest rules for every blocked
// domain. When idle, clear the rules. If the service is unreachable we
// KEEP the last known rules in place — safer to leave a block in place
// than to release it on transient failure.

const SERVICE_URL = "http://127.0.0.1:8765";
const POLL_ALARM = "focus-lock-poll";
const POLL_INTERVAL_MIN = 0.0833; // 5 seconds — minimum allowed in MV3
const STORAGE_KEY = "lastStatus";

// Rule IDs are integers; we partition 1..N for blocked domains.
const RULE_ID_BASE = 1000;

function buildRules(domains) {
  return domains.map((domain, i) => ({
    id: RULE_ID_BASE + i,
    priority: 1,
    action: { type: "block" },
    condition: {
      urlFilter: `||${domain}^`,
      resourceTypes: [
        "main_frame",
        "sub_frame",
        "stylesheet",
        "script",
        "image",
        "font",
        "object",
        "xmlhttprequest",
        "ping",
        "csp_report",
        "media",
        "websocket",
        "other",
      ],
    },
  }));
}

async function applyRules(domains) {
  const existing = await chrome.declarativeNetRequest.getDynamicRules();
  const removeRuleIds = existing.map((r) => r.id);
  const addRules = buildRules(domains);
  await chrome.declarativeNetRequest.updateDynamicRules({
    removeRuleIds,
    addRules,
  });
}

async function fetchStatus() {
  const res = await fetch(`${SERVICE_URL}/api/status`, {
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`status ${res.status}`);
  return res.json();
}

async function poll() {
  let status;
  try {
    status = await fetchStatus();
  } catch (err) {
    // Service unreachable. Keep current rules — don't auto-unblock.
    await chrome.storage.local.set({
      lastError: { at: Date.now(), message: String(err) },
    });
    return;
  }
  const desiredDomains = status.active ? (status.blocked_domains || []) : [];
  const desiredSet = new Set(desiredDomains.map((d) => d.toLowerCase()));
  const current = await chrome.declarativeNetRequest.getDynamicRules();
  const currentSet = new Set(
    current.map((r) => r.condition.urlFilter.replace(/^\|\||\^$/g, ""))
  );
  const same =
    desiredSet.size === currentSet.size &&
    [...desiredSet].every((d) => currentSet.has(d));
  if (!same) {
    await applyRules(desiredDomains);
  }
  await chrome.storage.local.set({
    [STORAGE_KEY]: { at: Date.now(), status, ruleCount: desiredDomains.length },
    lastError: null,
  });
}

chrome.runtime.onInstalled.addListener(async () => {
  await chrome.alarms.create(POLL_ALARM, {
    periodInMinutes: POLL_INTERVAL_MIN,
  });
  poll();
});

chrome.runtime.onStartup.addListener(async () => {
  await chrome.alarms.create(POLL_ALARM, {
    periodInMinutes: POLL_INTERVAL_MIN,
  });
  poll();
});

chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === POLL_ALARM) poll();
});
