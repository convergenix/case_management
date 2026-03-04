// // Copyright (c) 2017, bobzz.zone@gmail.com and contributors
// // For license information, please see license.txt

frappe.ui.form.on('Time Tracking', {

    onload(frm) {
        if (frm.is_new() && !frm.doc.employee) {
            frappe.db.get_value(
                "Employee",
                { user_id: frappe.session.user },
                "name",
                (r) => { if (r && r.name) frm.set_value("employee", r.name); }
            );
        }
    },

    refresh(frm) {
        const isActive = frm.doc.docstatus === 1
            && frm.doc.start_time
            && !frm.doc.end_time;

        if (isActive) {
            _initTimer(frm);
        }
    }
});


function _initTimer(frm) {
    const STORAGE_KEY = `tt_timer_${frm.doc.name}`;
    const ONE_HOUR    = 3600;

    // ── Restore or initialise state ───────────────────────────────────────────
    let state = _loadState(STORAGE_KEY);

    if (!state) {
        state = { remaining: ONE_HOUR, isPaused: false, lastTickedAt: Date.now() };
        _saveState(STORAGE_KEY, state);
    } else {
        if (!state.isPaused) {
            const elapsed   = Math.floor((Date.now() - state.lastTickedAt) / 1000);
            state.remaining = Math.max(0, state.remaining - elapsed);
        }
        state.lastTickedAt = Date.now();
        _saveState(STORAGE_KEY, state);
    }

    // ── Timer widget ──────────────────────────────────────────────────────────
    if (frm.fields_dict.timer) {
        frm.fields_dict.timer.$wrapper.html(`
            <div style="
                font-family: 'Courier New', monospace;
                background: #f8f9fa;
                border: 1px solid #dee2e6;
                border-radius: 6px;
                padding: 12px 18px;
                display: inline-flex;
                gap: 32px;
                align-items: center;
                margin: 4px 0;
            ">
                <div>
                    <div style="font-size: 11px; color: #6c757d; text-transform: uppercase; letter-spacing: 0.05em;">Current Time</div>
                    <div id="tt_live_clock" style="font-size: 22px; font-weight: bold; color: #212529;">--:--:--</div>
                </div>
                <div style="width: 1px; height: 40px; background: #dee2e6;"></div>
                <div>
                    <div style="font-size: 11px; color: #6c757d; text-transform: uppercase; letter-spacing: 0.05em;">Next Alert In</div>
                    <div id="tt_countdown" style="font-size: 22px; font-weight: bold; color: #e67e22;">--:--:--</div>
                </div>
                <div style="width: 1px; height: 40px; background: #dee2e6;"></div>
                <div>
                    <div style="font-size: 11px; color: #6c757d; text-transform: uppercase; letter-spacing: 0.05em;">Elapsed</div>
                    <div id="tt_elapsed" style="font-size: 22px; font-weight: bold; color: #27ae60;">--:--:--</div>
                </div>
                <div>
                    <span id="tt_pause_badge" style="
                        display: none;
                        background: #f39c12; color: #fff;
                        font-size: 11px; padding: 2px 8px;
                        border-radius: 12px; font-family: sans-serif;
                    ">⏸ PAUSED</span>
                </div>
            </div>
        `);
    }

    // ── Interval ID stored here so ALL buttons can reach it ───────────────────
    let countdownIntervalId = null;
    let clockIntervalId     = null;

    function _stopAllIntervals() {
        if (countdownIntervalId) { clearInterval(countdownIntervalId); countdownIntervalId = null; }
        if (clockIntervalId)     { clearInterval(clockIntervalId);     clockIntervalId     = null; }
    }

    // ── Buttons ───────────────────────────────────────────────────────────────
    frm.add_custom_button("🛑 Stop Timer", () => {
        frappe.confirm(
            "Are you sure you want to stop and finalise this time tracking entry?",
            () => {
                _stopAllIntervals();   // ← kill both intervals immediately
                _clearState(STORAGE_KEY);

                // Freeze the countdown display so it doesn't flicker
                const cdEl = document.getElementById("tt_countdown");
                if (cdEl) { cdEl.innerText = "00:00:00"; cdEl.style.color = "#6c757d"; }

                frappe.call({
                    method: "case_management.case_management.doctype.time_tracking.time_tracking.finalize_time_tracking",
                    args: { time_tracking: frm.doc.name },
                    callback: () => {
                        frappe.show_alert({ message: "Time Tracking Stopped", indicator: "red" });
                        frm.reload_doc();
                    }
                });
            }
        );
    }).addClass("btn-danger");

    frm.add_custom_button("⏸ Pause", () => {
        if (!state.isPaused) {
            state.isPaused     = true;
            state.lastTickedAt = Date.now();
            _saveState(STORAGE_KEY, state);
            frappe.show_alert({ message: "Timer Paused", indicator: "orange" });
            _updatePauseBadge(true);
        }
    }).addClass("btn-warning");

    frm.add_custom_button("▶ Resume", () => {
        if (state.isPaused) {
            state.isPaused     = false;
            state.lastTickedAt = Date.now();
            _saveState(STORAGE_KEY, state);
            frappe.show_alert({ message: "Timer Resumed", indicator: "green" });
            _updatePauseBadge(false);
        }
    }).addClass("btn-success");

    // ── Helpers ───────────────────────────────────────────────────────────────
    function _updatePauseBadge(paused) {
        const badge = document.getElementById("tt_pause_badge");
        if (badge) badge.style.display = paused ? "inline-block" : "none";
    }

    function _fmt(totalSeconds) {
        const h = Math.floor(totalSeconds / 3600);
        const m = Math.floor((totalSeconds % 3600) / 60);
        const s = totalSeconds % 60;
        return `${String(h).padStart(2,"0")}:${String(m).padStart(2,"0")}:${String(s).padStart(2,"0")}`;
    }

    // ── Live clock ────────────────────────────────────────────────────────────
    clockIntervalId = setInterval(() => {
        const el = document.getElementById("tt_live_clock");
        if (el) el.innerText = new Date().toLocaleTimeString();
    }, 1000);

    // ── Countdown + elapsed ───────────────────────────────────────────────────
    const startMs = frm.doc.start_time
        ? moment(frm.doc.start_time).valueOf()
        : Date.now();

    _updatePauseBadge(state.isPaused);

    countdownIntervalId = setInterval(() => {
        if (!state.isPaused) {
            state.remaining    = Math.max(0, state.remaining - 1);
            state.lastTickedAt = Date.now();
            _saveState(STORAGE_KEY, state);
        }

        const cdEl = document.getElementById("tt_countdown");
        if (cdEl) {
            cdEl.innerText   = _fmt(state.remaining);
            cdEl.style.color = state.isPaused
                ? "#f39c12"
                : state.remaining < 300 ? "#e74c3c" : "#e67e22";
        }

        const elEl = document.getElementById("tt_elapsed");
        if (elEl) elEl.innerText = _fmt(Math.floor((Date.now() - startMs) / 1000));

        // Prompt at zero
        if (state.remaining === 0 && !state.isPaused) {
            state.remaining = ONE_HOUR;
            _saveState(STORAGE_KEY, state);

            frappe.confirm(
                `⏰ An hour has passed on Matter <b>${frm.doc.matter}</b>
                (Client: <b>${frm.doc.matter_name || "Unknown"}</b>).<br><br>
                Would you like to keep working?`,
                () => {
                    frappe.show_alert({ message: "Timer reset for another hour", indicator: "blue" });
                },
                () => {
                    _stopAllIntervals();
                    _clearState(STORAGE_KEY);
                    frappe.call({
                        method: "case_management.case_management.doctype.time_tracking.time_tracking.finalize_time_tracking",
                        args: { time_tracking: frm.doc.name },
                        callback: () => {
                            frappe.show_alert("Time Tracking Ended");
                            frm.reload_doc();
                        }
                    });
                }
            );
        }
    }, 1000);
}


// ─── localStorage helpers ─────────────────────────────────────────────────────
function _loadState(key) {
    try { const r = localStorage.getItem(key); return r ? JSON.parse(r) : null; }
    catch { return null; }
}
function _saveState(key, state) {
    try { localStorage.setItem(key, JSON.stringify(state)); } catch {}
}
function _clearState(key) {
    try { localStorage.removeItem(key); } catch {}
}