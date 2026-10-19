(function () {
  "use strict";

  const API_BASE = (window.FILE_MEMORY_API_BASE || "").replace(/\/$/, "");
  const state = { mode: "semantic", query: "", folders: [], settings: { tracking_paused: false, ai_mode: "no_ai", ignored_extensions: [] }, lastSearch: "" };
  const $ = (selector) => document.querySelector(selector);
  const input = $("#search-input");
  const resultsList = $("#results-list");
  const folderCount = $("#folder-count");
  const toast = $("#toast");
  let toastTimer;

  function endpoint(path) { return API_BASE + path; }

  async function request(path, options) {
    const response = await fetch(endpoint(path), Object.assign({
      headers: { Accept: "application/json" }
    }, options || {}));
    let payload = null;
    const contentType = response.headers.get("content-type") || "";
    if (contentType.includes("json")) {
      try { payload = await response.json(); } catch (_) { payload = null; }
    } else {
      try { payload = await response.text(); } catch (_) { payload = null; }
    }
    if (!response.ok) {
      const message = payload && typeof payload === "object" && (payload.detail || payload.error || payload.message);
      throw new Error(message || "The local API returned an error (" + response.status + ").");
    }
    return payload;
  }

  const api = {
    search(query, semantic) {
      return request("/api/search?q=" + encodeURIComponent(query) + "&semantic=" + String(semantic));
    },
    folders() { return request("/api/folders"); },
    settings() { return request("/api/settings"); },
    saveSettings(settings) {
      return request("/api/settings", { method: "POST", headers: { "Content-Type": "application/json", Accept: "application/json" }, body: JSON.stringify(settings) });
    },
    rebuild() {
      return request("/api/rebuild", { method: "POST", headers: { "Content-Type": "application/json", Accept: "application/json" }, body: "{}" });
    },
    forgetFile(path) {
      return request("/api/files/forget", { method: "POST", headers: { "Content-Type": "application/json", Accept: "application/json" }, body: JSON.stringify({ path: path, confirmed: true }) });
    },
    addFolder(path) {
      return request("/api/folders", { method: "POST", headers: { "Content-Type": "application/json", Accept: "application/json" }, body: JSON.stringify({ path: path }) });
    },
    removeFolder(path) {
      return request("/api/folders?path=" + encodeURIComponent(path) + "&confirmed=true", { method: "DELETE" });
    },
    openFile(path) {
      return request("/api/actions/open-file", { method: "POST", headers: { "Content-Type": "application/json", Accept: "application/json" }, body: JSON.stringify({ path: path }) });
    },
    openFolder(path) {
      return request("/api/actions/open-folder", { method: "POST", headers: { "Content-Type": "application/json", Accept: "application/json" }, body: JSON.stringify({ path: path }) });
    }
  };

  function setState(name) {
    ["empty", "loading", "error", "no-results"].forEach(function (key) {
      $("#state-" + key).hidden = key !== name;
    });
    resultsList.hidden = name !== "results";
  }

  function showError(error, title) {
    $("#error-title").textContent = title || "Memory is offline.";
    $("#error-message").textContent = error && error.message ? error.message : "The local API could not be reached. Start the backend and try again.";
    setState("error");
  }

  function showToast(message, isError) {
    clearTimeout(toastTimer);
    toast.textContent = message;
    toast.classList.toggle("error", Boolean(isError));
    toast.hidden = false;
    toastTimer = setTimeout(function () { toast.hidden = true; }, 4200);
  }

  function asArray(payload, keys) {
    if (Array.isArray(payload)) return payload;
    if (payload && typeof payload === "object") {
      for (const key of keys) if (Array.isArray(payload[key])) return payload[key];
    }
    return [];
  }

  function value(record, keys, fallback) {
    for (const key of keys) if (record && record[key] !== undefined && record[key] !== null && record[key] !== "") return record[key];
    return fallback;
  }

  function formatDate(raw) {
    if (!raw) return "Date unavailable";
    const date = new Date(raw);
    if (Number.isNaN(date.getTime())) return String(raw);
    return new Intl.DateTimeFormat(undefined, { year: "numeric", month: "short", day: "numeric" }).format(date);
  }

  function scoreLabel(record) {
    const raw = value(record, ["score", "similarity", "rank"], null);
    if (raw === null || raw === "") return "Match found";
    const number = Number(raw);
    if (!Number.isFinite(number)) return String(raw);
    if (number >= 0 && number <= 1) return Math.round(number * 100) + "% match";
    return Math.round(number) + " score";
  }

  function renderResults(payload, mode) {
    const records = asArray(payload, ["results", "matches", "items", "data"]);
    if (!records.length) { resultsList.replaceChildren(); setState("no-results"); return; }
    resultsList.replaceChildren(...records.map(function (record) {
      const path = String(value(record, ["path", "file_path"], ""));
      const filename = String(value(record, ["filename", "name", "file_name"], path ? path.split(/[\\/]/).pop() : "Unnamed file"));
      const note = String(value(record, ["note", "snippet", "description"], "No note saved for this file."));
      const date = formatDate(value(record, ["modified_at", "updated_at", "created_at", "indexed_at", "date"], ""));
      const matchType = String(value(record, ["match_type", "type"], mode === "semantic" ? "Meaning" : "Exact words"));
      const card = document.createElement("article");
      card.className = "result-card";
       card.innerHTML = "<div class=\"result-top\"><h3 class=\"result-name\"></h3><span class=\"result-score\"></span></div>" +
       "<p class=\"result-note\"></p><div class=\"result-meta\"><div class=\"meta-item\"><span class=\"meta-label\">Path</span><span class=\"path-value\"></span></div><div class=\"meta-item\"><span class=\"meta-label\">Updated</span><span class=\"date-value\"></span></div><div class=\"meta-item\"><span class=\"meta-label\">Match</span><span class=\"match-value\"></span></div></div>" +
       "<div class=\"result-actions\"><button class=\"action-button primary open-file\" type=\"button\">Open file</button><button class=\"action-button open-folder\" type=\"button\">Open folder</button><button class=\"action-button copy-path\" type=\"button\">Copy path</button><button class=\"action-button forget-file\" type=\"button\">Forget</button></div>";
      card.querySelector(".result-name").textContent = filename;
      card.querySelector(".result-score").textContent = scoreLabel(record);
      card.querySelector(".result-note").textContent = note;
      card.querySelector(".path-value").textContent = path || "Path unavailable";
      card.querySelector(".date-value").textContent = date;
      card.querySelector(".match-value").textContent = matchType;
      card.querySelector(".open-file").addEventListener("click", function () { runAction(api.openFile, path, "File opened."); });
      card.querySelector(".open-folder").addEventListener("click", function () {
        const folder = path.replace(/[\\/][^\\/]*$/, "") || path;
        runAction(api.openFolder, folder, "Folder opened.");
      });
       card.querySelector(".copy-path").addEventListener("click", function () { copyPath(path); });
       card.querySelector(".forget-file").addEventListener("click", async function () {
         if (!window.confirm("Forget this indexed file? The real file will not be deleted.")) return;
         try { await api.forgetFile(path); card.remove(); showToast("File forgotten from memory.", false); }
         catch (error) { showToast(error.message, true); }
       });
      return card;
    }));
    setState("results");
  }

  async function runAction(action, path, successMessage) {
    if (!path) { showToast("This result has no usable path.", true); return; }
    try { await action(path); showToast(successMessage, false); }
    catch (error) { showToast(error.message || "The local API could not be reached.", true); }
  }

  async function copyPath(path) {
    if (!path) { showToast("This result has no usable path.", true); return; }
    try {
      if (!navigator.clipboard || !navigator.clipboard.writeText) throw new Error("Clipboard access is unavailable in this browser.");
      await navigator.clipboard.writeText(path);
      showToast("Path copied.", false);
    } catch (error) { showToast(error.message, true); }
  }

  async function search() {
    const query = input.value.trim();
    state.query = query;
    if (!query) { resultsList.replaceChildren(); setState("empty"); input.focus(); return; }
    state.lastSearch = query;
    setState("loading");
    try { renderResults(await api.search(query, state.mode === "semantic"), state.mode); }
    catch (error) { showError(error); }
  }

  function updateFolderCount() { folderCount.textContent = String(state.folders.length); }

  function renderFolders() {
    const list = $("#folders-list");
    list.replaceChildren(...state.folders.map(function (folder) {
      const path = typeof folder === "string" ? folder : value(folder, ["path"], "");
      const item = document.createElement("li"); item.className = "folder-row";
      const pathElement = document.createElement("span"); pathElement.className = "folder-path"; pathElement.textContent = path;
       const remove = document.createElement("button"); remove.className = "folder-remove"; remove.type = "button"; remove.textContent = "Remove"; remove.setAttribute("aria-label", "Remove " + path);
       remove.addEventListener("click", async function () {
         if (!window.confirm("Stop watching this folder? Indexed files will remain until you forget them.")) return;
         remove.disabled = true;
        try { await api.removeFolder(path); state.folders = state.folders.filter(function (item) { return (typeof item === "string" ? item : item.path) !== path; }); renderFolders(); updateFolderCount(); showToast("Folder removed.", false); }
        catch (error) { remove.disabled = false; setFolderMessage(error.message, true); }
      });
      item.append(pathElement, remove); return item;
    }));
  }

  function setFolderMessage(message, error) { const element = $("#folder-state"); element.textContent = message || ""; element.classList.toggle("error", Boolean(error)); }

  async function loadFolders() {
    try { state.folders = asArray(await api.folders(), ["folders", "items", "data"]); updateFolderCount(); renderFolders(); setFolderMessage(""); }
    catch (error) { state.folders = []; folderCount.textContent = "—"; renderFolders(); setFolderMessage("API unavailable: " + error.message, true); }
  }

  function openFolders() {
    const dialog = $("#folders-dialog");
    if (typeof dialog.showModal === "function") dialog.showModal();
    else dialog.setAttribute("open", "");
    loadFolders();
    setTimeout(function () { $("#folder-input").focus(); }, 30);
  }

  function closeFolders() { const dialog = $("#folders-dialog"); if (dialog.open && dialog.close) dialog.close(); else dialog.removeAttribute("open"); }

  function renderSettings() {
    $("#pause-tracking").checked = Boolean(state.settings.tracking_paused);
    $("#ai-mode").value = state.settings.ai_mode || "no_ai";
    $("#ignored-extensions").value = (state.settings.ignored_extensions || []).join(", ");
  }

  async function loadSettings() {
    try { state.settings = await api.settings(); renderSettings(); }
    catch (error) { $("#settings-state").textContent = "API unavailable: " + error.message; }
  }

  function openSettings() {
    const dialog = $("#settings-dialog");
    if (typeof dialog.showModal === "function") dialog.showModal();
    else dialog.setAttribute("open", "");
    loadSettings();
  }

  function closeSettings() { const dialog = $("#settings-dialog"); if (dialog.open && dialog.close) dialog.close(); else dialog.removeAttribute("open"); }

  $("#search-form").addEventListener("submit", function (event) { event.preventDefault(); search(); });
  $("#retry-button").addEventListener("click", search);
  document.querySelectorAll(".mode-button").forEach(function (button) {
    button.addEventListener("click", function () {
      state.mode = button.dataset.mode;
      document.querySelectorAll(".mode-button").forEach(function (other) { const active = other === button; other.classList.toggle("active", active); other.setAttribute("aria-pressed", String(active)); });
      if (state.query) search();
    });
  });
  $("#folders-open").addEventListener("click", openFolders);
  $("#folders-open-secondary").addEventListener("click", openFolders);
  $("#folders-close").addEventListener("click", closeFolders);
  $("#folders-dialog").addEventListener("click", function (event) { if (event.target === event.currentTarget) closeFolders(); });
  $("#settings-open").addEventListener("click", openSettings);
  $("#settings-close").addEventListener("click", closeSettings);
  $("#settings-dialog").addEventListener("click", function (event) { if (event.target === event.currentTarget) closeSettings(); });
  $("#settings-form").addEventListener("submit", async function (event) {
    event.preventDefault();
    const stateElement = $("#settings-state");
    stateElement.textContent = "Saving locally…";
    try {
      state.settings = await api.saveSettings({
        tracking_paused: $("#pause-tracking").checked,
        ai_mode: $("#ai-mode").value,
        ignored_extensions: $("#ignored-extensions").value
      });
      renderSettings(); stateElement.textContent = "Settings saved locally.";
    } catch (error) { stateElement.textContent = error.message; }
  });
  $("#rebuild-index").addEventListener("click", async function () {
    const stateElement = $("#settings-state"); stateElement.textContent = "Rebuilding…";
    try { const result = await api.rebuild(); stateElement.textContent = "Index rebuilt. " + result.total + " files stored."; }
    catch (error) { stateElement.textContent = error.message; }
  });
  $("#folder-form").addEventListener("submit", async function (event) {
    event.preventDefault();
    const folderInput = $("#folder-input"); const path = folderInput.value.trim();
    if (!path) return;
    const submit = event.currentTarget.querySelector(".submit-button"); submit.disabled = true; setFolderMessage("Adding folder…");
    try { const added = await api.addFolder(path); state.folders = state.folders.concat([added && added.path ? added : { path: path }]); renderFolders(); updateFolderCount(); folderInput.value = ""; setFolderMessage("Folder added."); }
    catch (error) { setFolderMessage("API unavailable: " + error.message, true); }
    finally { submit.disabled = false; }
  });

  loadFolders();
  loadSettings();
}());
