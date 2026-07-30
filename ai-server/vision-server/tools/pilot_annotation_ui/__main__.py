"""Run the local, one-rater-at-a-time annotation UI."""

from __future__ import annotations

import argparse
import base64
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk

import cv2

from app.vision.pilot_annotation_ui import AnnotationWorkspace


class AnnotationApp:
    def __init__(self, workspace: AnnotationWorkspace) -> None:
        self.workspace = workspace
        self.root = tk.Tk()
        self.root.title(f"Face-Fit Annotation — {workspace.rater_id}")
        self.capture = cv2.VideoCapture(str(workspace.video_path))
        if not self.capture.isOpened():
            raise RuntimeError("could not open input video")
        self.duration_ms = int(self.capture.get(cv2.CAP_PROP_FRAME_COUNT) /
                               self.capture.get(cv2.CAP_PROP_FPS) * 1000)
        self.current_timestamp_ms = workspace.answers[0]["start_timestamp_ms"]
        self.playing = False
        self.start_value: int | None = None
        self.end_value: int | None = None
        self._photo = None
        self._build()
        self.seek(self.current_timestamp_ms)
        self.refresh_events()

    def _build(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=1)
        header = ttk.Label(
            self.root,
            text=(f"{self.workspace.rater_id} | {self.workspace.session_id} | "
                  "Observable annotation only"),
        )
        header.grid(row=0, column=0, sticky="w", padx=10, pady=8)
        main = ttk.Frame(self.root, padding=10)
        main.grid(row=1, column=0, sticky="nsew")
        main.columnconfigure(0, weight=3)
        main.columnconfigure(1, weight=2)
        self.video_label = ttk.Label(main, text="Loading video frame")
        self.video_label.grid(row=0, column=0, sticky="nsew")
        right = ttk.Frame(main)
        right.grid(row=0, column=1, sticky="nsew", padx=(12, 0))
        self.timestamp_label = ttk.Label(right, text="0 ms")
        self.timestamp_label.grid(row=0, column=0, sticky="w")
        controls = ttk.Frame(right)
        controls.grid(row=1, column=0, sticky="ew", pady=5)
        ttk.Button(controls, text="Play/Pause", command=self.toggle_play).grid(row=0, column=0)
        for col, delta in enumerate((-500, -100, 100, 500), start=1):
            ttk.Button(controls, text=f"{delta:+d} ms", command=lambda d=delta: self.seek(self.current_timestamp_ms + d)).grid(row=0, column=col)
        ttk.Label(right, text="Answer interval").grid(row=2, column=0, sticky="w")
        self.answer_box = ttk.Combobox(right, state="readonly", values=[
            f"{a['answer_id']} [{a['start_timestamp_ms']},{a['end_timestamp_ms']})"
            for a in self.workspace.answers
        ])
        self.answer_box.current(0)
        self.answer_box.grid(row=3, column=0, sticky="ew")
        ttk.Button(right, text="Go to Answer", command=self.goto_answer).grid(row=4, column=0, sticky="w", pady=4)
        timing = ttk.Frame(right)
        timing.grid(row=5, column=0, sticky="ew", pady=4)
        self.start_label = ttk.Label(timing, text="Start: not set")
        self.end_label = ttk.Label(timing, text="End: not set")
        self.start_label.grid(row=0, column=0, sticky="w")
        self.end_label.grid(row=1, column=0, sticky="w")
        ttk.Button(timing, text="Capture start", command=self.capture_start).grid(row=0, column=1)
        ttk.Button(timing, text="Capture end", command=self.capture_end).grid(row=1, column=1)
        ttk.Label(right, text="Label").grid(row=6, column=0, sticky="w")
        self.label_box = ttk.Combobox(right, state="readonly", values=[x["label_id"] for x in self.workspace.labels])
        self.label_box.current(0)
        self.label_box.bind("<<ComboboxSelected>>", lambda _event: self.update_direction_choices())
        self.label_box.grid(row=7, column=0, sticky="ew")
        ttk.Label(right, text="Direction").grid(row=8, column=0, sticky="w")
        self.direction_box = ttk.Combobox(right, state="readonly")
        self.direction_box.grid(row=9, column=0, sticky="ew")
        self.update_direction_choices()
        ttk.Button(right, text="Add event", command=self.add_event).grid(row=10, column=0, sticky="w", pady=4)
        self.tree = ttk.Treeview(right, columns=("answer", "label", "range"), show="headings", height=12)
        for name, title in (("answer", "Answer"), ("label", "Label"), ("range", "Range")):
            self.tree.heading(name, text=title)
        self.tree.grid(row=11, column=0, sticky="nsew")
        buttons = ttk.Frame(right)
        buttons.grid(row=12, column=0, sticky="w", pady=4)
        ttk.Button(buttons, text="Load selected", command=self.load_selected).grid(row=0, column=0)
        ttk.Button(buttons, text="Update selected", command=self.update_selected).grid(row=0, column=1)
        ttk.Button(buttons, text="Delete selected", command=self.delete_selected).grid(row=0, column=2)
        footer = ttk.Frame(self.root, padding=10)
        footer.grid(row=2, column=0, sticky="ew")
        ttk.Button(footer, text="Save draft", command=self.save_draft).grid(row=0, column=0)
        ttk.Button(footer, text="Complete annotation", command=self.complete).grid(row=0, column=1, padx=6)

    def update_direction_choices(self) -> None:
        label = next(x for x in self.workspace.labels if x["label_id"] == self.label_box.get())
        values = list(label["allowed_directions"]) if label["requires_direction"] else ["null"]
        self.direction_box["values"] = values
        self.direction_box.current(0)

    def goto_answer(self) -> None:
        self.seek(self.workspace.answers[self.answer_box.current()]["start_timestamp_ms"])

    def seek(self, timestamp_ms: int) -> None:
        self.current_timestamp_ms = max(0, min(timestamp_ms, self.duration_ms - 1))
        self.capture.set(cv2.CAP_PROP_POS_MSEC, self.current_timestamp_ms)
        ok, frame = self.capture.read()
        if ok:
            frame = cv2.resize(frame, (640, 360))
            ok, encoded = cv2.imencode(".png", frame)
            if ok:
                self._photo = tk.PhotoImage(data=base64.b64encode(encoded.tobytes()))
                self.video_label.configure(image=self._photo, text="")
        self.timestamp_label.configure(text=f"{self.current_timestamp_ms} ms")

    def toggle_play(self) -> None:
        self.playing = not self.playing
        if self.playing:
            self._tick()

    def _tick(self) -> None:
        if not self.playing:
            return
        self.seek(self.current_timestamp_ms + 33)
        self.root.after(33, self._tick)

    def capture_start(self) -> None:
        self.start_value = self.current_timestamp_ms
        self.start_label.configure(text=f"Start: {self.start_value} ms")

    def capture_end(self) -> None:
        self.end_value = self.current_timestamp_ms
        self.end_label.configure(text=f"End: {self.end_value} ms")

    def _direction(self) -> str | None:
        return None if self.direction_box.get() == "null" else self.direction_box.get()

    def add_event(self) -> None:
        try:
            if self.start_value is None or self.end_value is None:
                raise ValueError("capture both start and end timestamps")
            answer = self.workspace.answer_for_timestamp(self.start_value)
            if answer is None:
                raise ValueError("event start must be inside an Answer interval")
            self.workspace.add_event(answer_id=answer["answer_id"], label_id=self.label_box.get(), direction=self._direction(), start_timestamp_ms=self.start_value, end_timestamp_ms=self.end_value)
            self.refresh_events()
        except (ValueError, KeyError) as exc:
            messagebox.showerror("Cannot add event", str(exc))

    def refresh_events(self) -> None:
        self.tree.delete(*self.tree.get_children())
        for event in self.workspace.events:
            self.tree.insert("", "end", iid=event["annotation_event_id"], values=(event["answer_id"], event["label_id"], f"[{event['start_timestamp_ms']},{event['end_timestamp_ms']})"))

    def load_selected(self) -> None:
        selection = self.tree.selection()
        if not selection:
            return
        event = next(x for x in self.workspace.events if x["annotation_event_id"] == selection[0])
        self.answer_box.current(next(i for i, a in enumerate(self.workspace.answers) if a["answer_id"] == event["answer_id"]))
        self.label_box.current([x["label_id"] for x in self.workspace.labels].index(event["label_id"]))
        self.update_direction_choices()
        self.direction_box.set(event["direction"] or "null")
        self.start_value, self.end_value = event["start_timestamp_ms"], event["end_timestamp_ms"]
        self.start_label.configure(text=f"Start: {self.start_value} ms")
        self.end_label.configure(text=f"End: {self.end_value} ms")
        self.seek(self.start_value)

    def update_selected(self) -> None:
        selection = self.tree.selection()
        try:
            if len(selection) != 1 or self.start_value is None or self.end_value is None:
                raise ValueError("select an event and capture both timestamps")
            answer = self.workspace.answers[self.answer_box.current()]
            self.workspace.update_event(selection[0], answer_id=answer["answer_id"], label_id=self.label_box.get(), direction=self._direction(), start_timestamp_ms=self.start_value, end_timestamp_ms=self.end_value)
            self.refresh_events()
        except (ValueError, KeyError) as exc:
            messagebox.showerror("Cannot update event", str(exc))

    def delete_selected(self) -> None:
        selection = self.tree.selection()
        if len(selection) == 1 and messagebox.askyesno("Delete event", "Delete the selected event?"):
            self.workspace.delete_event(selection[0])
            self.refresh_events()

    def save_draft(self) -> None:
        self.workspace.save_draft()
        messagebox.showinfo("Draft saved", str(self.workspace.draft_path))

    def complete(self) -> None:
        empty = not self.workspace.events
        if empty and not messagebox.askyesno("Empty annotation", "No events are recorded. Complete an empty annotation?"):
            return
        replace = self.workspace.result_path.exists()
        if replace and not messagebox.askyesno("Replace result", "A completed result exists. Replace it?"):
            return
        try:
            path = self.workspace.complete(confirm_empty_events=empty, confirm_replace_existing=replace)
            messagebox.showinfo("Annotation completed", str(path))
        except (ValueError, FileExistsError) as exc:
            messagebox.showerror("Cannot complete", str(exc))

    def run(self) -> None:
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.mainloop()

    def close(self) -> None:
        self.capture.release()
        self.root.destroy()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--rater-id", required=True, choices=("RATER_A", "RATER_B"))
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    workspace = AnnotationWorkspace(
        root / "data" / "output" / "pilot_annotation" / args.session_id,
        session_id=args.session_id,
        rater_id=args.rater_id,
    )
    AnnotationApp(workspace).run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
