// Copyright (c) 2017, bobzz.zone@gmail.com and contributors
// For license information, please see license.txt

frappe.ui.form.on('Time Tracking', {
    refresh(frm) {
        if (!frm.is_new() && frm.doc.status === "Time Tracking Started") {
            let countdownIntervalId = null;

            // 🚨 Add Stop Timer button at the top
            frm.add_custom_button("🛑 Stop Timer", () => {
                clearInterval(countdownIntervalId); // stop countdown
                frappe.call({
                    method: "case_management.case_management.doctype.time_tracking.time_tracking.finalize_time_tracking",
                    args: { time_tracking: frm.doc.name },
                    callback: () => {
                        frappe.show_alert("Time Tracking Stopped");
                        frm.reload_doc();
                    }
                });
            }).addClass("btn-danger");

            // 🖥️ Add timer display UI
            if (frm.fields_dict.timer) {
                frm.fields_dict.timer.$wrapper.html(`
                    <div style="font-family: monospace; font-size: 16px;">
                        <b>🕒 Live Clock:</b> <span id="live_clock">--:--:--</span><br>
                        <b>⏳ Countdown:</b> <span id="countdown_timer">--:--:--</span>
                    </div>
                `);
            }

            function updateLiveClock() {
                const now = new Date();
                const clockEl = document.getElementById("live_clock");
                if (clockEl) clockEl.innerText = now.toLocaleTimeString();
                setTimeout(updateLiveClock, 1000);
            }

            let remaining = 3600; // 1 hour in seconds

            function updateCountdown() {
                const timerEl = document.getElementById("countdown_timer");
                if (timerEl) {
                    const hours = Math.floor(remaining / 3600);
                    const minutes = Math.floor((remaining % 3600) / 60);
                    const seconds = remaining % 60;
                    timerEl.innerText = `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
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

            updateLiveClock();
            countdownIntervalId = setInterval(updateCountdown, 1000);
        }
    }
});
