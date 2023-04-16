import csv
import threading
import time
import tkinter as tk
from datetime import datetime
from tkinter import ttk, filedialog, messagebox
from ttkthemes import ThemedTk
import ffmpeg
import requests

# Add a global variable to control recording state
recording = False


def get_stream_metadata(stream_url):
    response = requests.get(stream_url, headers={'Icy-MetaData': '1'}, stream=True)
    icy_metaint_header = response.headers.get('icy-metaint')
    if icy_metaint_header is None:
        raise ValueError("The stream does not have any metadata.")
    metaint = int(icy_metaint_header)
    return response, metaint


def process_metadata(chunk, metadata_file):
    metadata_length = chunk[0] * 16
    if metadata_length > 0:
        metadata = chunk[1:metadata_length + 1].decode('utf-8', errors='ignore')
        _, title = '', ''
        if 'StreamTitle=' in metadata:
            stream_title = metadata.split('StreamTitle=')[1].split(';')[0].strip('\'"')
            if '-' in stream_title:
                artist, title = stream_title.split('-', 1)
                print(f"Artist: {artist.strip()}, Title: {title.strip()}")
                csv.writer(metadata_file).writerow(
                    [artist.strip(), title.strip(), datetime.now().strftime('%Y-%m-%d %H:%M:%S')])


def update_progress_bar(start_time, duration_in_seconds):
    global recording
    while recording:
        elapsed_seconds = time.perf_counter() - start_time
        progress_var.set(int((elapsed_seconds / duration_in_seconds) * 100))
        root.update_idletasks()

        if elapsed_seconds >= duration_in_seconds:
            recording = False
            break

        time.sleep(1)

    # If recording has finished, set progress bar to 100%
    progress_var.set(100)


def process_stream_metadata(url, metaint, metadata_file, duration_in_seconds):
    start_time = time.perf_counter()
    response = requests.get(url, headers={'Icy-MetaData': '1'}, stream=True)

    while recording:
        audio_data = bytearray()
        while len(audio_data) < metaint:
            audio_data_chunk = response.raw.read(metaint - len(audio_data))
            if not audio_data_chunk:
                break
            audio_data.extend(audio_data_chunk)

        metadata_length = response.raw.read(1)
        if not metadata_length:
            break

        metadata_length = metadata_length[0] * 16
        if metadata_length > 0:
            metadata = response.raw.read(metadata_length).decode('utf-8', errors='ignore')
            _, title = '', ''
            if 'StreamTitle=' in metadata:
                stream_title = metadata.split('StreamTitle=')[1].split(';')[0].strip('\'"')
                if '-' in stream_title:
                    artist, title = stream_title.split('-', 1)
                    print(f"Artist: {artist.strip()}, Title: {title.strip()}")
                    csv.writer(metadata_file).writerow(
                        [artist.strip(), title.strip(), datetime.now().strftime('%Y-%m-%d %H:%M:%S')])

        elapsed_seconds = time.perf_counter() - start_time
        if elapsed_seconds >= duration_in_seconds:
            break


def record_icecast_stream(url, output_folder, output_file, duration_in_seconds):
    global recording
    try:
        response, metaint = get_stream_metadata(url)
    except ValueError as e:
        messagebox.showerror("Error", str(e))
        return

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    file_path = f"{output_folder}/{output_file}_{timestamp}.mp3"
    metadata_file_path = f"{output_folder}/{output_file}_metadata_{timestamp}.csv"

    with open(metadata_file_path, 'w', newline='', encoding="utf-8") as metadata_file:
        csv_writer = csv.writer(metadata_file)
        csv_writer.writerow(['Artist', 'Title', 'Start Time'])

        print(f"Recording started. Saving to {file_path}")
        start_time = time.perf_counter()

        # Start the ffmpeg process
        recording = True
        process = (
            ffmpeg
            .input(url)
            .output(file_path, t=duration_in_seconds, codec="copy")
            .global_args("-loglevel", "warning")
            .run_async(pipe_stdout=True, pipe_stderr=True)
        )

        progress_thread = threading.Thread(target=update_progress_bar, args=(start_time, duration_in_seconds))
        progress_thread.start()

        # Process metadata in a separate thread
        metadata_thread = threading.Thread(target=process_stream_metadata,
                                           args=(url, metaint, metadata_file, duration_in_seconds))
        metadata_thread.start()

        # Wait for the recording to finish
        process.wait()
        progress_thread.join()
        metadata_thread.join()

    if recording:
        print(f"Recording finished. Saved to {file_path}")
        recording = False
        progress_var.set(0)
        messagebox.showinfo("Success", f"Recording finished. Saved to {file_path}")
    else:
        print("Recording cancelled")
        progress_var.set(0)
        recording = False


def start_recording():
    global recording
    try:
        recording = True
        url = url_entry.get()
        output_file = file_entry.get()
        duration = int(duration_entry.get())
        duration_unit = duration_unit_var.get()

        # Convert duration to seconds based on the selected unit
        if duration_unit == "minutes":
            duration_in_seconds = duration * 60
        elif duration_unit == "hours":
            duration_in_seconds = duration * 60 * 60
        else:
            duration_in_seconds = duration

        # Use threading to run the record_icecast_stream function in a separate thread
        record_thread = threading.Thread(target=record_icecast_stream,
                                         args=(url, output_folder.get(), output_file, duration_in_seconds))
        record_thread.start()
    except Exception as e:
        messagebox.showerror("Error", str(e))
        recording = False


def cancel_recording():
    global recording
    recording = False


def browse_output_folder():
    folder = filedialog.askdirectory()
    output_folder.set(folder)


# Create the main window
root = ThemedTk(theme="arc")  # Choose a modern theme
root.title("StreamSniffer V0.01")

# Create input fields and labels
url_label = ttk.Label(root, text="Stream URL:")
url_label.grid(row=0, column=0, padx=5, pady=2)
url_entry = ttk.Entry(root, width=50)
url_entry.grid(row=0, column=1, padx=5, pady=2)

file_label = ttk.Label(root, text="Output file name:")
file_label.grid(row=1, column=0, padx=5, pady=2)
file_entry = ttk.Entry(root, width=50)
file_entry.grid(row=1, column=1, padx=5, pady=2)

duration_label = ttk.Label(root, text="Duration:")
duration_label.grid(row=2, column=0, padx=5, pady=2)
duration_entry = ttk.Entry(root, width=50)
duration_entry.grid(row=2, column=1, padx=5, pady=2)

# Add the option menu for duration units
duration_unit_var = tk.StringVar(root)
duration_unit_var.set("seconds")
duration_unit_menu = ttk.OptionMenu(root, duration_unit_var, "seconds", "seconds", "minutes", "hours")
duration_unit_menu.grid(row=2, column=2, padx=5, pady=2)

output_folder = tk.StringVar()
folder_label = ttk.Label(root, text="Save to:")
folder_label.grid(row=3, column=0, padx=5, pady=2)
folder_entry = ttk.Entry(root, textvariable=output_folder, width=50)
folder_entry.grid(row=3, column=1, padx=5, pady=2)
folder_button = ttk.Button(root, text="Browse", command=browse_output_folder, width=12)
folder_button.grid(row=3, column=2, padx=5, pady=2)

# Create the record button
record_button = ttk.Button(root, text="Start Recording", command=start_recording)
record_button.grid(row=5, column=2, padx=5, pady=2)

# Create the cancel button
cancel_button = ttk.Button(root, text="Cancel Recording", command=cancel_recording)
cancel_button.grid(row=6, column=2, padx=5, pady=2)

# Create the progress bar
progress_var = tk.DoubleVar()
progress_label = ttk.Label(root, text="Progress:", width=12)
progress_label.grid(row=5, column=0, padx=5, pady=2)
progress_bar = ttk.Progressbar(root, orient="horizontal", length=300, mode="determinate", variable=progress_var)
progress_bar.grid(row=5, column=1, padx=5, pady=2)

# Start the main loop
root.mainloop()
