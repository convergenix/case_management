console.log(">>> file_list.js loaded");

frappe.listview_settings['Item'] = {
    onload: function(listview) {
        console.log(">>> File ListView loaded", listview);

        // Prevent duplicate buttons
        if (listview.page._nav_buttons_added) return;
        listview.page._nav_buttons_added = true;

        listview.page.add_inner_button(__('Previous'), () => {
            console.log(">>> Previous clicked");
            listview.start = Math.max(0, (listview.start || 0) - (listview.page_length || 20));
            console.log(">>> New start:", listview.start);
            listview.refresh();
        });

        listview.page.add_inner_button(__('Next'), () => {
            console.log(">>> Next clicked");
            listview.start = (listview.start || 0) + (listview.page_length || 20);
            console.log(">>> New start:", listview.start);
            listview.refresh();
        });
    }
};
