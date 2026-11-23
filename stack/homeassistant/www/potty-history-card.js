// The History tab of the Potty page: the newest check photos, each with
// Clean, Poop and Delete buttons. Tapping a photo opens it full screen inside
// the app, with the same buttons and arrows (or a swipe) to the next photo.
// Reads sensor.potty_history and calls the potty_handle_answer and
// potty_delete_photo scripts with the viewer's own Home Assistant login.
// Loaded through frontend: extra_module_url in configuration.yaml; deployed to
// /config/www/potty-history-card.js. HA serves it with a 31-day cache, so bump
// ?v= there after changing this file.

const ANSWERS = { poop: "Poop", clean: "Clean" };
const HOSE = { rinsed: "Rinsed", stopped: "Stopped early", skipped: "Skipped, patio not clear", paused: "Paused in settings" };

const CSS = `
  .summary { padding: 0 16px 8px; color: var(--secondary-text-color); }
  .error { padding: 0 16px 8px; color: var(--error-color); }
  .row {
    display: flex; gap: 12px; align-items: center;
    padding: 10px 16px; border-top: 1px solid var(--divider-color);
  }
  .row img { width: 88px; height: 88px; border-radius: 6px; display: block; cursor: zoom-in; }
  .info { flex: 1; min-width: 0; line-height: 1.5; }
  .time { font-weight: 500; }
  .hose { color: var(--secondary-text-color); font-size: 0.9em; }
  .buttons { display: flex; flex-direction: column; gap: 6px; }
  button {
    font: inherit; font-size: 0.9em; padding: 6px 10px; min-width: 92px;
    border-radius: 6px; border: 1px solid var(--divider-color);
    background: var(--card-background-color); color: var(--primary-text-color);
  }
  button.on { background: var(--primary-color); color: var(--text-primary-color, #fff); border-color: var(--primary-color); }
  button.armed { background: var(--error-color); color: #fff; border-color: var(--error-color); }
  button:disabled { opacity: 0.5; }
  button { display: inline-flex; align-items: center; gap: 6px; --mdc-icon-size: 18px; }
`;

// The full-screen viewer lives on document.body, outside Home Assistant's
// layout, so nothing in the page can clip it.
const VIEWER_CSS = `
  .backdrop {
    position: fixed; inset: 0; z-index: 9999; box-sizing: border-box;
    display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 12px;
    padding: max(16px, env(safe-area-inset-top)) 16px max(16px, env(safe-area-inset-bottom));
    background: #000; color: #fff;
    font-family: Roboto, -apple-system, "Segoe UI", sans-serif;
  }
  .top { width: 100%; max-width: 640px; display: flex; align-items: center; gap: 12px; }
  .caption { flex: 1; line-height: 1.4; }
  .caption .time { font-weight: 500; font-size: 1.1em; }
  .caption .hose { color: #bbb; font-size: 0.9em; }
  img { max-width: 100%; max-height: calc(100vh - 220px); object-fit: contain; border-radius: 6px; touch-action: pan-y; }
  .error { color: #ff8a80; min-height: 1.2em; }
  .bar { display: flex; gap: 8px; flex-wrap: wrap; justify-content: center; align-items: center; }
  button {
    font: inherit; font-size: 1em; padding: 10px 14px; border-radius: 8px;
    border: 1px solid #555; background: #222; color: #fff;
  }
  button.on { background: #03a9f4; border-color: #03a9f4; }
  button.armed { background: #db4437; border-color: #db4437; }
  button:disabled { opacity: 0.35; }
  button { display: inline-flex; align-items: center; gap: 6px; --mdc-icon-size: 20px; }
  .close { padding: 8px; }
`;

class PottyHistoryCard extends HTMLElement {
  setConfig(config) {
    this._entity = config.entity || "sensor.potty_history";
    this._items = [];
    this._viewing = null;
  }

  set hass(hass) {
    this._hass = hass;
    const state = hass.states[this._entity];
    const items = (state && state.attributes.items) || [];
    const key = JSON.stringify(items);
    if (key !== this._key) {
      this._key = key;
      this._render(items);
    }
  }

  getCardSize() {
    return 12;
  }

  disconnectedCallback() {
    this._closeViewer();
  }

  _el(tag, props = {}, children = []) {
    const el = document.createElement(tag);
    Object.assign(el, props);
    el.append(...children);
    return el;
  }

  // A button with a Material Design icon (Home Assistant's ha-icon) and text.
  _button(icon, text, props = {}) {
    const button = this._el("button", props);
    this._label(button, icon, text);
    return button;
  }

  _label(button, icon, text) {
    const parts = [this._el("ha-icon", { icon })];
    if (text) parts.push(this._el("span", { textContent: text }));
    button.replaceChildren(...parts);
  }

  _render(items) {
    this._items = items;
    if (!this._card) {
      this.attachShadow({ mode: "open" });
      this._card = this._el("ha-card", { header: "History" });
      this.shadowRoot.append(this._el("style", { textContent: CSS }), this._card);
    }
    const poop = items.filter((i) => i.label === "poop").length;
    const clean = items.filter((i) => i.label === "clean").length;
    this._error = this._el("div", { className: "error" });
    const summary = this._el("div", {
      className: "summary",
      textContent: items.length
        ? `Last ${items.length} checks: ${poop} poop, ${clean} clean, ${items.length - poop - clean} not answered. Tap a photo to see it big.`
        : "No check photos yet.",
    });
    this._card.replaceChildren(summary, this._error, ...items.map((i) => this._row(i)));

    // Keep an open viewer in step: a new label shows at once, and after a
    // delete it moves on to the photo that took the deleted one's place.
    if (this._viewing) {
      if (!items.some((i) => i.id === this._viewing)) {
        const next = items[Math.min(this._viewIndex, items.length - 1)];
        this._viewing = next ? next.id : null;
      }
      if (this._viewing) this._showViewer();
      else this._closeViewer();
    }
  }

  // Clean, Poop and Delete for one photo; errors go to errorEl.
  _answerButtons(item, errorEl) {
    const cleanButton = this._button("mdi:check-circle-outline", "Clean", { className: item.label === "clean" ? "on" : "" });
    const poopButton = this._button("mdi:emoticon-poop", "Poop", { className: item.label === "poop" ? "on" : "" });
    const deleteButton = this._button("mdi:delete-outline", "Delete");
    cleanButton.onclick = () => this._call("potty_handle_answer", { answer: "CLEAN", shot: item.id }, cleanButton, errorEl);
    poopButton.onclick = () => this._call("potty_handle_answer", { answer: "POOP", shot: item.id }, poopButton, errorEl);

    // Two taps: the first arms the button for 4 seconds.
    deleteButton.onclick = () => {
      if (deleteButton.classList.contains("armed")) {
        this._call("potty_delete_photo", { shot: item.id }, deleteButton, errorEl);
        return;
      }
      deleteButton.classList.add("armed");
      this._label(deleteButton, "mdi:delete-alert-outline", "Tap to delete");
      setTimeout(() => {
        deleteButton.classList.remove("armed");
        this._label(deleteButton, "mdi:delete-outline", "Delete");
      }, 4000);
    };
    return [cleanButton, poopButton, deleteButton];
  }

  _row(item) {
    const answer = ANSWERS[item.label] || "Not answered";
    const model = item.prob === null || item.prob === undefined ? "" : ` (model ${Math.round(item.prob * 100)}%)`;
    const photo = this._el("img", { src: `/local/potty/thumbs/${item.id}.jpg`, alt: `Check photo ${item.time}`, loading: "lazy" });
    photo.onclick = () => this._openViewer(item.id);
    const info = this._el("div", { className: "info" }, [
      this._el("div", { className: "time", textContent: item.time }),
      this._el("div", { textContent: answer + model }),
      this._el("div", { className: "hose", textContent: `Hose: ${HOSE[item.hose] || "—"}` }),
    ]);
    const buttons = this._el("div", { className: "buttons" }, this._answerButtons(item, this._error));
    return this._el("div", { className: "row" }, [photo, info, buttons]);
  }

  _openViewer(id) {
    this._viewing = id;
    if (!this._viewer) {
      this._viewer = document.createElement("div");
      const root = this._viewer.attachShadow({ mode: "open" });
      this._viewerBox = this._el("div", { className: "backdrop" });
      root.append(this._el("style", { textContent: VIEWER_CSS }), this._viewerBox);

      // Tap outside the photo and buttons to close; swipe to change photo.
      this._viewerBox.onclick = (e) => {
        if (e.target === this._viewerBox) this._closeViewer();
      };
      this._viewerBox.addEventListener("touchstart", (e) => {
        this._touchX = e.changedTouches[0].clientX;
      }, { passive: true });
      this._viewerBox.addEventListener("touchend", (e) => {
        const dx = e.changedTouches[0].clientX - this._touchX;
        if (Math.abs(dx) > 60) this._stepViewer(dx < 0 ? 1 : -1);
      });
      this._onKey = (e) => {
        if (e.key === "Escape") this._closeViewer();
        else if (e.key === "ArrowRight") this._stepViewer(1);
        else if (e.key === "ArrowLeft") this._stepViewer(-1);
      };
    }
    if (!this._viewer.isConnected) {
      document.body.append(this._viewer);
      document.addEventListener("keydown", this._onKey);
    }
    this._showViewer();
  }

  _closeViewer() {
    this._viewing = null;
    if (this._viewer && this._viewer.isConnected) {
      this._viewer.remove();
      document.removeEventListener("keydown", this._onKey);
    }
  }

  // Newer photos are first in the list, so +1 is the next older one.
  _stepViewer(delta) {
    const next = this._items[this._viewIndex + delta];
    if (next) {
      this._viewing = next.id;
      this._showViewer();
    }
  }

  _showViewer() {
    const items = this._items;
    this._viewIndex = items.findIndex((i) => i.id === this._viewing);
    const item = items[this._viewIndex];
    if (!item) {
      this._closeViewer();
      return;
    }
    const answer = ANSWERS[item.label] || "Not answered";
    const close = this._button("mdi:close", "", { className: "close", title: "Close" });
    close.onclick = () => this._closeViewer();
    const top = this._el("div", { className: "top" }, [
      this._el("div", { className: "caption" }, [
        this._el("div", { className: "time", textContent: `${item.time} · ${answer}` }),
        this._el("div", { className: "hose", textContent: `Hose: ${HOSE[item.hose] || "—"} · ${this._viewIndex + 1} of ${items.length}` }),
      ]),
      close,
    ]);
    const photo = this._el("img", { src: `/local/potty/${item.id}.jpg`, alt: `Check photo ${item.time}` });
    const error = this._el("div", { className: "error" });
    const newer = this._button("mdi:chevron-left", "Newer", { disabled: this._viewIndex === 0 });
    const older = this._button("mdi:chevron-right", "Older", { disabled: this._viewIndex === items.length - 1 });
    older.append(older.firstChild);
    newer.onclick = () => this._stepViewer(-1);
    older.onclick = () => this._stepViewer(1);
    const answers = this._el("div", { className: "bar" }, this._answerButtons(item, error));
    const nav = this._el("div", { className: "bar" }, [newer, older]);
    this._viewerBox.replaceChildren(top, photo, error, answers, nav);
  }

  async _call(script, data, button, errorEl) {
    button.disabled = true;
    errorEl.textContent = "";
    try {
      await this._hass.callService("script", script, data);
    } catch (err) {
      errorEl.textContent = `Didn't work: ${err.message || err}`;
    } finally {
      button.disabled = false;
    }
  }
}

customElements.define("potty-history-card", PottyHistoryCard);
