// Copyright (c) 2017, bobzz.zone@gmail.com and contributors
// For license information, please see license.txt

// frappe.ui.form.on('Time Tracking', {
//     validate(frm) {
//         if (!frm.doc.start_time || !frm.doc.end_time) {
//             frappe.throw("Please enter both Start Time and End Time before submitting.");
//         }
//     },

//     refresh(frm) {
//         // Only show the clock if time tracking is running
//         if (!frm.is_new() && frm.doc.status === "Time Tracking Started") {
//             const totalSeconds = Math.floor(frm.doc.time * 3600);

//             frm.fields_dict.timer.$wrapper.html(`
//                 <div style="font-family: monospace; font-size: 16px;">
//                     <b>🕒 Live Clock:</b> <span id="live_clock">--:--:--</span><br>
//                     <b>⏳ Countdown:</b> <span id="countdown_timer">--:--:--</span>
//                 </div>
//             `);

//             let remaining = totalSeconds;

//             function updateLiveClock() {
//                 const now = new Date();
//                 const clockEl = document.getElementById("live_clock");
//                 if (clockEl) clockEl.innerText = now.toLocaleTimeString();
//                 setTimeout(updateLiveClock, 1000);
//             }

//             function updateCountdown() {
//                 const hrs = Math.floor(remaining / 3600);
//                 const mins = Math.floor((remaining % 3600) / 60);
//                 const secs = remaining % 60;

//                 const timerEl = document.getElementById("countdown_timer");
//                 if (timerEl) {
//                     timerEl.innerText = `${hrs.toString().padStart(2, '0')}:${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
//                 }

//                 if (remaining > 0) {
//                     remaining--;
//                     setTimeout(updateCountdown, 1000);
//                 } else {
//                     frappe.call({
//                         method: "case_management.case_management.doctype.time_tracking.time_tracking.end_time_tracking",
//                         args: { time_tracking: frm.doc.name },
//                         callback: () => {
//                             frappe.show_alert("⏰ Time Tracking Ended");
//                             frm.reload_doc();
//                         }
//                     });
//                 }
//             }

//             // Start both timers
//             updateLiveClock();
//             updateCountdown();
//         }
//     }
// });

// // ✅ Handle notification
// frappe.realtime.on("time_tracking_ended", function (data) {
//     if (cur_frm && cur_frm.doc.name === data.time_tracking) {
//         frappe.show_alert({
//             message: `⏰ Time Tracking Ended for Matter <b>${data.matter_id}</b> (Client: ${data.client_name})`,
//             indicator: 'red'
//         });
//         cur_frm.reload_doc();
//     }
// });




frappe.ui.form.on('Time Tracking', {
    refresh(frm) {
        if (!frm.is_new() && frm.doc.status === "Time Tracking Started") {
            let intervalId = null;

            function startReminderLoop() {
                // Clear any previous interval
                if (intervalId) clearInterval(intervalId);

                intervalId = setInterval(() => {
                    frappe.confirm(
                        `⏰ Would you like to continue working on this Matter <b>${frm.doc.matter}</b> (Client: <b>${frm.doc.matter_name || "Unknown"}</b>)?`,
                        () => {
                            // YES: Do nothing, continue tracking
                        },
                        () => {
                            // NO: End time tracking
                            frappe.call({
                                method: "case_management.case_management.doctype.time_tracking.time_tracking.finalize_time_tracking",
                                args: { time_tracking: frm.doc.name },
                                callback: () => {
                                    frappe.show_alert("Time Tracking Ended");
                                    frm.reload_doc();
                                }
                            });
                            clearInterval(intervalId); // Stop further prompts
                        }
                    );
                }, 60 * 1000); // Every 1 minute
            }

            startReminderLoop();
        }
    }
});
