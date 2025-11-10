// Copyright (c) 2017, bobzz.zone@gmail.com and contributors
// For license information, please see license.txt

frappe.ui.form.on('Time Tracking', {
    refresh(frm) {
        if (!frm.is_new() && frm.doc.status === "Time Tracking Started") {
            let countdownIntervalId = null;
            let remaining = 3600; // 1 hour in seconds
            let isPaused = false;

            // 🛑 Stop Timer
            frm.add_custom_button("🛑 Stop Timer", () => {
                clearInterval(countdownIntervalId);
                frappe.call({
                    method: "case_management.case_management.doctype.time_tracking.time_tracking.finalize_time_tracking",
                    args: { time_tracking: frm.doc.name },
                    callback: () => {
                        frappe.show_alert("Time Tracking Stopped");
                        frm.reload_doc();
                    }
                });
            }).addClass("btn-danger");

            // ⏸ Pause Countdown
            frm.add_custom_button("⏸ Pause Countdown", () => {
                if (!isPaused) {
                    isPaused = true;
                    frappe.show_alert("Countdown Paused");
                }
            }).addClass("btn-warning");

            // ▶ Continue Countdown
            frm.add_custom_button("▶ Continue Countdown", () => {
                if (isPaused) {
                    isPaused = false;
                    frappe.show_alert("Countdown Continued");
                }
            }).addClass("btn-success");

            // 🖥️ Timer UI
            if (frm.fields_dict.timer) {
                frm.fields_dict.timer.$wrapper.html(`
                    <div style="font-family: monospace; font-size: 16px;">
                        <b>🕒 Live Clock:</b> <span id="live_clock">--:--:--</span><br>
                        <b>⏳ Countdown:</b> <span id="countdown_timer">--:--:--</span>
                    </div>
                `);
            }

            // ⏰ Always running live clock
            function updateLiveClock() {
                const now = new Date();
                const clockEl = document.getElementById("live_clock");
                if (clockEl) clockEl.innerText = now.toLocaleTimeString();
                setTimeout(updateLiveClock, 1000);
            }

            // ⏳ Countdown logic (pausable)
            function updateCountdown() {
                if (isPaused) return; // don't tick if paused
                const timerEl = document.getElementById("countdown_timer");
                if (timerEl) {
                    const h = Math.floor(remaining / 3600);
                    const m = Math.floor((remaining % 3600) / 60);
                    const s = remaining % 60;
                    timerEl.innerText = `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
                }

                if (remaining > 0) {
                    remaining--;
                } else {
                    showContinuePrompt();
                    remaining = 3600;
                }
            }

            function showContinuePrompt() {
                frappe.confirm(
                    `⏰ Would you like to continue working on this Matter <b>${frm.doc.matter}</b> (Client: <b>${frm.doc.matter_name || "Unknown"}</b>)?`,
                    () => { remaining = 3600; },
                    () => {
                        clearInterval(countdownIntervalId);
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

            // Start everything
            updateLiveClock();
            countdownIntervalId = setInterval(updateCountdown, 1000);
        }
    }
});
