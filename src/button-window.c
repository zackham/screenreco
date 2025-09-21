#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <fcntl.h>
#include <gtk/gtk.h>

static void on_cancel_clicked(GtkWidget *widget, gpointer data) {
    // Create cancel marker FIRST
    FILE *f = fopen("/tmp/screen-recorder-cancel", "w");
    if (f) fclose(f);
    // Then stop recording
    system("pkill -INT wf-recorder");
    // Then create stop marker
    f = fopen("/tmp/stop-screen-recorder-overlay", "w");
    if (f) fclose(f);
    gtk_main_quit();
}

static void on_save_clicked(GtkWidget *widget, gpointer data) {
    // Create save marker FIRST
    FILE *f = fopen("/tmp/screen-recorder-save", "w");
    if (f) fclose(f);
    // Then stop recording
    system("pkill -INT wf-recorder");
    // Then create stop marker
    f = fopen("/tmp/stop-screen-recorder-overlay", "w");
    if (f) fclose(f);
    gtk_main_quit();
}

static gboolean check_stop_file(gpointer data) {
    if (access("/tmp/stop-screen-recorder-overlay", F_OK) == 0) {
        gtk_main_quit();
        return FALSE;
    }
    return TRUE;
}


int main(int argc, char *argv[]) {
    if (argc != 2) {
        fprintf(stderr, "Usage: %s \"x,y widthxheight\"\n", argv[0]);
        return 1;
    }
    
    int rec_x, rec_y, rec_width, rec_height;
    sscanf(argv[1], "%d,%d %dx%d", &rec_x, &rec_y, &rec_width, &rec_height);
    
    gtk_init(&argc, &argv);
    
    GtkWidget *window = gtk_window_new(GTK_WINDOW_TOPLEVEL);
    gtk_window_set_title(GTK_WINDOW(window), "screen-recorder-controls");
    gtk_window_set_decorated(GTK_WINDOW(window), FALSE);
    gtk_window_set_keep_above(GTK_WINDOW(window), TRUE);
    gtk_window_set_resizable(GTK_WINDOW(window), FALSE);
    gtk_window_set_skip_taskbar_hint(GTK_WINDOW(window), TRUE);
    gtk_window_set_skip_pager_hint(GTK_WINDOW(window), TRUE);
    
    // Style the window
    GtkCssProvider *provider = gtk_css_provider_new();
    gtk_css_provider_load_from_data(provider,
        "window { background-color: rgba(0, 0, 0, 0.9); }\n"
        ".cancel-button { background-color: #662222; color: white; font-weight: bold; }\n"
        ".cancel-button:hover { background-color: #882222; }\n"
        ".save-button { background-color: #226622; color: white; font-weight: bold; }\n"
        ".save-button:hover { background-color: #228822; }\n",
        -1, NULL);
    gtk_style_context_add_provider_for_screen(gdk_screen_get_default(),
        GTK_STYLE_PROVIDER(provider), GTK_STYLE_PROVIDER_PRIORITY_APPLICATION);
    
    // Create button box with buttons
    GtkWidget *hbox = gtk_box_new(GTK_ORIENTATION_HORIZONTAL, 10);
    gtk_container_set_border_width(GTK_CONTAINER(hbox), 10);
    
    // Cancel button
    GtkWidget *cancel_btn = gtk_button_new_with_label("✗ Cancel");
    gtk_widget_set_size_request(cancel_btn, 80, 30);
    GtkStyleContext *cancel_style = gtk_widget_get_style_context(cancel_btn);
    gtk_style_context_add_class(cancel_style, "cancel-button");
    g_signal_connect(cancel_btn, "clicked", G_CALLBACK(on_cancel_clicked), NULL);
    
    // Save button  
    GtkWidget *save_btn = gtk_button_new_with_label("✓ Save");
    gtk_widget_set_size_request(save_btn, 80, 30);
    GtkStyleContext *save_style = gtk_widget_get_style_context(save_btn);
    gtk_style_context_add_class(save_style, "save-button");
    g_signal_connect(save_btn, "clicked", G_CALLBACK(on_save_clicked), NULL);
    
    gtk_box_pack_start(GTK_BOX(hbox), cancel_btn, FALSE, FALSE, 0);
    gtk_box_pack_start(GTK_BOX(hbox), save_btn, FALSE, FALSE, 0);
    
    gtk_container_add(GTK_CONTAINER(window), hbox);
    
    
    gtk_widget_show_all(window);
    
    // Check for stop file periodically
    g_timeout_add(500, check_stop_file, NULL);
    
    gtk_main();
    
    return 0;
}