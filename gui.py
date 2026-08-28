"""
gui.py
------
CustomTkinter front-end for the video converter.

Keeps conversion work on a background thread so the UI never freezes,
and pushes progress/log updates back to the main thread via a queue.
"""

import os
import threading
import queue
import customtkinter as ctk
from tkinter import filedialog, messagebox

import converter as conv

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class VideoConverterApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Video Converter")
        self.geometry("640x760")
        self.minsize(600, 680)

        self.input_path = None
        self.output_dir = None
        self.msg_queue = queue.Queue()
        self.worker_thread = None

        self._build_layout()
        self._poll_queue()

    # ------------------------------------------------------------------ UI

    def _build_layout(self):
        pad = {"padx": 16, "pady": 8}

        # --- File selection ---
        file_frame = ctk.CTkFrame(self)
        file_frame.pack(fill="x", **pad)

        self.file_label = ctk.CTkLabel(
            file_frame, text="No file selected", anchor="w", wraplength=420
        )
        self.file_label.pack(side="left", fill="x", expand=True, padx=(12, 8), pady=12)

        ctk.CTkButton(file_frame, text="Choose File", command=self.choose_file, width=120).pack(
            side="right", padx=12, pady=12
        )

        # --- Mode selection (Video->Video / Video->MP3) ---
        mode_frame = ctk.CTkFrame(self)
        mode_frame.pack(fill="x", **pad)

        ctk.CTkLabel(mode_frame, text="Conversion type:", anchor="w").pack(
            side="top", anchor="w", padx=12, pady=(12, 0)
        )

        self.mode_var = ctk.StringVar(value="video")
        self.mode_switch = ctk.CTkSegmentedButton(
            mode_frame,
            values=["Video → Video", "Video → Audio"],
            command=self.on_mode_change,
        )
        self.mode_switch.set("Video → Video")
        self.mode_switch.pack(fill="x", padx=12, pady=(6, 12))

        # --- Video options panel ---
        self.video_panel = ctk.CTkFrame(self)
        self.video_panel.pack(fill="x", **pad)
        self._build_video_panel(self.video_panel)

        # --- Audio (MP3) options panel ---
        self.audio_panel = ctk.CTkFrame(self)
        self._build_audio_panel(self.audio_panel)
        # not packed initially — shown only in mp3 mode

        # --- Output folder ---
        out_frame = ctk.CTkFrame(self)
        out_frame.pack(fill="x", **pad)

        self.output_label = ctk.CTkLabel(
            out_frame, text="Output folder: (same as input by default)", anchor="w", wraplength=420
        )
        self.output_label.pack(side="left", fill="x", expand=True, padx=(12, 8), pady=12)

        ctk.CTkButton(out_frame, text="Choose Folder", command=self.choose_output_dir, width=120).pack(
            side="right", padx=12, pady=12
        )

        # --- Convert button ---
        self.convert_btn = ctk.CTkButton(
            self, text="Convert", height=42, font=("", 16, "bold"), command=self.start_conversion
        )
        self.convert_btn.pack(fill="x", padx=16, pady=(4, 8))

        # --- Progress bar ---
        self.progress_bar = ctk.CTkProgressBar(self)
        self.progress_bar.set(0)
        self.progress_bar.pack(fill="x", padx=16, pady=(0, 4))

        self.status_label = ctk.CTkLabel(self, text="Ready.", anchor="w")
        self.status_label.pack(fill="x", padx=16, pady=(0, 8))

        # --- Log box ---
        self.log_box = ctk.CTkTextbox(self, height=120)
        self.log_box.pack(fill="both", expand=True, padx=16, pady=(0, 16))
        self.log_box.configure(state="disabled")

    def _build_video_panel(self, parent):
        ctk.CTkLabel(parent, text="Video Settings", font=("", 14, "bold")).grid(
            row=0, column=0, columnspan=2, sticky="w", padx=12, pady=(12, 2)
        )
        ctk.CTkLabel(
            parent,
            text="Defaults match a common broadcast/OTT delivery spec — change any field freely.",
            text_color="gray60",
            wraplength=520,
            justify="left",
        ).grid(row=1, column=0, columnspan=2, sticky="w", padx=12, pady=(0, 10))

        # Output format
        ctk.CTkLabel(parent, text="Output format:").grid(row=2, column=0, sticky="w", padx=12, pady=6)
        self.format_var = ctk.StringVar(value="mp4")
        self.format_menu = ctk.CTkOptionMenu(
            parent,
            variable=self.format_var,
            values=list(conv.VIDEO_FORMATS.keys()),
            command=self.on_format_change,
        )
        self.format_menu.grid(row=2, column=1, sticky="ew", padx=12, pady=6)

        # Video codec (synced to format)
        ctk.CTkLabel(parent, text="Video codec:").grid(row=3, column=0, sticky="w", padx=12, pady=6)
        self.codec_var = ctk.StringVar(value="h264")
        self.codec_menu = ctk.CTkOptionMenu(
            parent, variable=self.codec_var, values=conv.VIDEO_FORMATS["mp4"]
        )
        self.codec_menu.grid(row=3, column=1, sticky="ew", padx=12, pady=6)

        # Resolution
        ctk.CTkLabel(parent, text="Resolution:").grid(row=4, column=0, sticky="w", padx=12, pady=6)
        self.res_var = ctk.StringVar(value="1920x1080 (Full HD)")
        ctk.CTkOptionMenu(
            parent, variable=self.res_var, values=list(conv.RESOLUTIONS.keys())
        ).grid(row=4, column=1, sticky="ew", padx=12, pady=6)

        # Frame rate
        ctk.CTkLabel(parent, text="Frame rate:").grid(row=5, column=0, sticky="w", padx=12, pady=6)
        self.fps_var = ctk.StringVar(value="Native (source frame rate)")
        ctk.CTkOptionMenu(
            parent, variable=self.fps_var, values=list(conv.FRAMERATES.keys())
        ).grid(row=5, column=1, sticky="ew", padx=12, pady=6)

        # Color space
        ctk.CTkLabel(parent, text="Color space:").grid(row=6, column=0, sticky="w", padx=12, pady=6)
        self.colorspace_var = ctk.StringVar(value="Rec.709 (SDR)")
        ctk.CTkOptionMenu(
            parent, variable=self.colorspace_var, values=list(conv.COLORSPACES.keys())
        ).grid(row=6, column=1, sticky="ew", padx=12, pady=6)

        # Bitrate slider
        min_br, max_br = conv.BITRATE_RANGE_MBPS
        ctk.CTkLabel(parent, text="Bitrate:").grid(row=7, column=0, sticky="w", padx=12, pady=6)
        bitrate_frame = ctk.CTkFrame(parent, fg_color="transparent")
        bitrate_frame.grid(row=7, column=1, sticky="ew", padx=12, pady=6)
        bitrate_frame.grid_columnconfigure(0, weight=1)

        self.bitrate_var = ctk.DoubleVar(value=conv.DEFAULT_BITRATE_MBPS)
        self.bitrate_label = ctk.CTkLabel(
            bitrate_frame, text=f"{conv.DEFAULT_BITRATE_MBPS} Mbps", width=70
        )

        def on_slide(value):
            self.bitrate_label.configure(text=f"{int(value)} Mbps")

        self.bitrate_slider = ctk.CTkSlider(
            bitrate_frame,
            from_=min_br, to=max_br,
            number_of_steps=(max_br - min_br),
            variable=self.bitrate_var,
            command=on_slide,
        )
        self.bitrate_slider.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.bitrate_label.grid(row=0, column=1)

        # Audio (options depend on chosen format)
        ctk.CTkLabel(parent, text="Audio:").grid(row=8, column=0, sticky="w", padx=12, pady=(6, 12))
        self.audio_var = ctk.StringVar(value=conv.AUDIO_PCM)
        self.audio_menu = ctk.CTkOptionMenu(
            parent,
            variable=self.audio_var,
            values=conv.AUDIO_OPTIONS_BY_CONTAINER["mp4"],
        )
        self.audio_menu.grid(row=8, column=1, sticky="ew", padx=12, pady=(6, 12))

        parent.grid_columnconfigure(1, weight=1)

    def _build_audio_panel(self, parent):
        ctk.CTkLabel(parent, text="Audio Extraction Settings", font=("", 14, "bold")).grid(
            row=0, column=0, columnspan=2, sticky="w", padx=12, pady=(12, 2)
        )
        ctk.CTkLabel(
            parent,
            text="Defaults match a common \"preferred\" speech-data spec (lossless, 24-bit, 48kHz, stereo).",
            text_color="gray60",
            wraplength=520,
            justify="left",
        ).grid(row=1, column=0, columnspan=2, sticky="w", padx=12, pady=(0, 10))

        # Output format
        ctk.CTkLabel(parent, text="Format:").grid(row=2, column=0, sticky="w", padx=12, pady=6)
        self.audio_format_var = ctk.StringVar(value="FLAC (lossless)")
        self.audio_format_menu = ctk.CTkOptionMenu(
            parent,
            variable=self.audio_format_var,
            values=conv.AUDIO_EXTRACT_FORMATS,
            command=self.on_audio_format_change,
        )
        self.audio_format_menu.grid(row=2, column=1, sticky="ew", padx=12, pady=6)

        # Bit depth (hidden for MP3, since compression makes it meaningless)
        self.bit_depth_row_label = ctk.CTkLabel(parent, text="Bit depth:")
        self.bit_depth_row_label.grid(row=3, column=0, sticky="w", padx=12, pady=6)
        self.bit_depth_var = ctk.StringVar(value="24-bit (preferred)")
        self.bit_depth_menu = ctk.CTkOptionMenu(
            parent, variable=self.bit_depth_var, values=conv.AUDIO_BIT_DEPTHS
        )
        self.bit_depth_menu.grid(row=3, column=1, sticky="ew", padx=12, pady=6)

        # MP3 bitrate (hidden unless MP3 is selected)
        self.mp3_extract_row_label = ctk.CTkLabel(parent, text="Bitrate:")
        self.mp3_extract_bitrate_var = ctk.StringVar(value="192k")
        self.mp3_extract_menu = ctk.CTkOptionMenu(
            parent, variable=self.mp3_extract_bitrate_var, values=conv.AUDIO_EXTRACT_BITRATES
        )
        # not gridded initially — only shown when format is MP3

        # Sample rate
        ctk.CTkLabel(parent, text="Sample rate:").grid(row=4, column=0, sticky="w", padx=12, pady=6)
        self.sample_rate_var = ctk.StringVar(value="48000 Hz (preferred)")
        ctk.CTkOptionMenu(
            parent, variable=self.sample_rate_var, values=list(conv.AUDIO_SAMPLE_RATES.keys())
        ).grid(row=4, column=1, sticky="ew", padx=12, pady=6)

        # Channels
        ctk.CTkLabel(parent, text="Channels:").grid(row=5, column=0, sticky="w", padx=12, pady=(6, 12))
        self.channels_var = ctk.StringVar(value="Stereo (preferred)")
        ctk.CTkOptionMenu(
            parent, variable=self.channels_var, values=list(conv.AUDIO_CHANNELS.keys())
        ).grid(row=5, column=1, sticky="ew", padx=12, pady=(6, 12))

        parent.grid_columnconfigure(1, weight=1)

    def on_audio_format_change(self, fmt):
        # MP3 has no meaningful "bit depth" — swap that row for a bitrate row.
        if fmt.startswith("MP3"):
            self.bit_depth_row_label.grid_remove()
            self.bit_depth_menu.grid_remove()
            self.mp3_extract_row_label.grid(row=3, column=0, sticky="w", padx=12, pady=6)
            self.mp3_extract_menu.grid(row=3, column=1, sticky="ew", padx=12, pady=6)
        else:
            self.mp3_extract_row_label.grid_remove()
            self.mp3_extract_menu.grid_remove()
            self.bit_depth_row_label.grid(row=3, column=0, sticky="w", padx=12, pady=6)
            self.bit_depth_menu.grid(row=3, column=1, sticky="ew", padx=12, pady=6)

    # ------------------------------------------------------------ callbacks

    def on_mode_change(self, value):
        self.video_panel.pack_forget()
        self.audio_panel.pack_forget()

        if value == "Video → Video":
            self.mode_var.set("video")
            self.video_panel.pack(fill="x", padx=16, pady=8, after=self.mode_switch.master)
        else:
            self.mode_var.set("audio")
            self.audio_panel.pack(fill="x", padx=16, pady=8, after=self.mode_switch.master)

    def on_format_change(self, fmt):
        # Sync codec choices to the selected container.
        codecs = conv.VIDEO_FORMATS[fmt]
        self.codec_menu.configure(values=codecs)
        if self.codec_var.get() not in codecs:
            self.codec_var.set(codecs[0])

        # Sync audio choices to the selected container (e.g. WebM can't
        # carry PCM audio — only Opus/Vorbis).
        audio_options = conv.AUDIO_OPTIONS_BY_CONTAINER[fmt]
        self.audio_menu.configure(values=audio_options)
        if self.audio_var.get() not in audio_options:
            self.audio_var.set(audio_options[0])

    def choose_file(self):
        path = filedialog.askopenfilename(
            title="Select a video file",
            filetypes=[
                ("Video files", "*.mp4 *.mkv *.mov *.avi *.webm *.flv *.wmv *.m4v"),
                ("All files", "*.*"),
            ],
        )
        if path:
            self.input_path = path
            self.file_label.configure(text=os.path.basename(path))

    def choose_output_dir(self):
        directory = filedialog.askdirectory(title="Select output folder")
        if directory:
            self.output_dir = directory
            self.output_label.configure(text=f"Output folder: {directory}")

    # ------------------------------------------------------------ conversion

    def start_conversion(self):
        if not self.input_path:
            messagebox.showwarning("No file", "Please choose an input video file first.")
            return

        try:
            conv.check_ffmpeg_installed()
        except conv.FFmpegNotFoundError as e:
            messagebox.showerror("FFmpeg not found", str(e))
            return

        if self.worker_thread and self.worker_thread.is_alive():
            messagebox.showinfo("Busy", "A conversion is already running.")
            return

        out_dir = self.output_dir or os.path.dirname(self.input_path)
        base_name = os.path.splitext(os.path.basename(self.input_path))[0]
        mode = self.mode_var.get()

        if mode == "video":
            fmt = self.format_var.get()
            output_path = os.path.join(out_dir, f"{base_name}_converted.{fmt}")
            cmd = conv.build_video_command(
                self.input_path,
                output_path,
                container=fmt,
                codec_key=self.codec_var.get(),
                resolution_key=self.res_var.get(),
                bitrate_mbps=int(self.bitrate_var.get()),
                framerate_key=self.fps_var.get(),
                colorspace_key=self.colorspace_var.get(),
                audio_label=self.audio_var.get(),
            )
        else:  # audio
            fmt = self.audio_format_var.get()
            ext = "flac" if fmt.startswith("FLAC") else "wav" if fmt.startswith("WAV") else "mp3"
            output_path = os.path.join(out_dir, f"{base_name}.{ext}")
            cmd = conv.build_audio_extract_command(
                self.input_path,
                output_path,
                format_key=fmt,
                bit_depth_key=self.bit_depth_var.get(),
                sample_rate_key=self.sample_rate_var.get(),
                channels_key=self.channels_var.get(),
                mp3_bitrate=self.mp3_extract_bitrate_var.get(),
            )

        self._log_clear()
        self._log(f"Command: {conv.command_to_string(cmd)}")
        self.status_label.configure(text="Starting conversion...")
        self.progress_bar.set(0)
        self.convert_btn.configure(state="disabled", text="Converting...")

        self.worker_thread = threading.Thread(
            target=self._run_conversion, args=(cmd, self.input_path, output_path), daemon=True
        )
        self.worker_thread.start()

    def _run_conversion(self, cmd, input_path, output_path):
        try:
            duration = conv.get_duration_seconds(input_path)
            conv.run_ffmpeg(
                cmd,
                total_duration=duration,
                on_progress=lambda p: self.msg_queue.put(("progress", p)),
                on_line=lambda l: self.msg_queue.put(("log", l)),
            )
            self.msg_queue.put(("done", output_path))
        except Exception as e:
            self.msg_queue.put(("error", str(e)))

    # ------------------------------------------------------------ queue poll

    def _poll_queue(self):
        try:
            while True:
                kind, payload = self.msg_queue.get_nowait()
                if kind == "progress":
                    self.progress_bar.set(payload / 100)
                    self.status_label.configure(text=f"Converting... {payload:.1f}%")
                elif kind == "log":
                    self._log(payload)
                elif kind == "done":
                    self.progress_bar.set(1)
                    self.status_label.configure(text="Done!")
                    self.convert_btn.configure(state="normal", text="Convert")
                    messagebox.showinfo("Success", f"Saved to:\n{payload}")
                elif kind == "error":
                    self.status_label.configure(text="Failed.")
                    self.convert_btn.configure(state="normal", text="Convert")
                    self._log("ERROR: " + payload)
                    messagebox.showerror("Conversion failed", payload)
        except queue.Empty:
            pass
        self.after(100, self._poll_queue)

    def _log(self, text):
        self.log_box.configure(state="normal")
        self.log_box.insert("end", text + "\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def _log_clear(self):
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.configure(state="disabled")


if __name__ == "__main__":
    app = VideoConverterApp()
    app.mainloop()