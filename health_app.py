import os
import re
import sqlite3
import tkinter as tk
from datetime import datetime
from tkinter import messagebox, ttk

import requests

DB_FILE = "patients.db"

EMAIL_PATTERN = r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}$"
API_KEY = os.environ.get("GEMINI_API_KEY", "")
MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
FIELDS = [
    ("full_name", "Full Name"),
    ("dob", "Date of Birth (dd/mm/yyyy)"),
    ("email", "Email Address"),
    ("glucose", "Glucose"),
    ("haemoglobin", "Haemoglobin"),
    ("cholesterol", "Cholesterol"),
]


# ---------- Database ----------
def db_connect():
    return sqlite3.connect(DB_FILE)


def init_db():
    with db_connect() as db:
        db.execute(
            """CREATE TABLE IF NOT EXISTS patients (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                full_name TEXT, dob TEXT, email TEXT UNIQUE,
                glucose REAL, haemoglobin REAL, cholesterol REAL, remarks TEXT)"""
        )


# ---------- Validation ----------
def validate(values, editing_id=None):
    """Returns (clean_values, list_of_errors)."""
    errors = []
    v = dict(values)

    if not re.fullmatch(r"[A-Za-z][A-Za-z .'-]*", v["full_name"]):
        errors.append("Full name must contain only letters and spaces.")

    try:
        dob = datetime.strptime(v["dob"].replace(".", "/"), "%d/%m/%Y")
        if dob.date() > datetime.now().date():
            errors.append("Date of birth cannot be in the future.")
        v["dob"] = dob.strftime("%d/%m/%Y")
    except ValueError:
        errors.append("Date of birth is not a valid date (use dd/mm/yyyy).")

    if not re.match(EMAIL_PATTERN, v["email"]):
        errors.append("Email address format is invalid.")
    else:
        with db_connect() as db:
            row = db.execute("SELECT id FROM patients WHERE lower(email)=lower(?)",
                             (v["email"],)).fetchone()
        if row and row[0] != editing_id:
            errors.append("This email already exists (duplicate record).")

    for key, label in (("glucose", "Glucose"), ("haemoglobin", "Haemoglobin"),
                       ("cholesterol", "Cholesterol")):
        try:
            v[key] = float(v[key])
            if v[key] <= 0:
                raise ValueError
        except ValueError:
            errors.append(f"{label} must be a positive number.")

    return v, errors

# ---------- AI API ----------
def get_remarks(v):
    if not API_KEY:
        return "AI unavailable: GEMINI_API_KEY not set"

    prompt = (
        "Based on these blood test values, give ONE short sentence (max 25 words) "
        "naming the possible health condition or risk "
        "(diabetes risk, anaemia, high cholesterol, or normal). "
        "Do not give a definite medical diagnosis.\n"
        f"DOB: {v['dob']}, Glucose: {v['glucose']} mg/dL, "
        f"Haemoglobin: {v['haemoglobin']} g/dL, "
        f"Cholesterol: {v['cholesterol']} mg/dL"
    )

    url = "https://generativelanguage.googleapis.com/v1beta/interactions"

    try:
        r = requests.post(
            url,
            headers={
                "x-goog-api-key": API_KEY,
                "Content-Type": "application/json"
            },
            json={
                "model": "gemini-3.5-flash",
                "input": prompt
            },
            timeout=120
        )

        r.raise_for_status()
        data = r.json()

        for step in reversed(data.get("steps", [])):
            if step.get("type") == "model_output":
                for content in step.get("content", []):
                    if content.get("type") == "text":
                        return content.get("text", "").strip()

        return "AI response received but no text was returned."

    except requests.exceptions.HTTPError as e:
        return f"AI API error {e.response.status_code}: {e.response.text[:300]}"

    except Exception as e:
        return f"AI failed: {type(e).__name__}: {str(e)[:200]}"
        # ---------- UI ----------
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Health Prediction Records")
        self.geometry("1200x560")
        self.selected_id = None
        self.entries = {}

        form = ttk.LabelFrame(self, text="Patient details")
        form.pack(fill="x", padx=10, pady=10)
        for i, (key, label) in enumerate(FIELDS):
            ttk.Label(form, text=label).grid(row=i // 3 * 2, column=i % 3, sticky="w", padx=8)
            entry = ttk.Entry(form, width=32)
            entry.grid(row=i // 3 * 2 + 1, column=i % 3, padx=8, pady=(0, 8))
            self.entries[key] = entry

        buttons = ttk.Frame(form)
        buttons.grid(row=4, column=0, columnspan=3, pady=6)
        ttk.Button(buttons, text="Add", command=self.add).pack(side="left", padx=4)
        ttk.Button(buttons, text="Update selected", command=self.update).pack(side="left", padx=4)
        ttk.Button(buttons, text="Delete selected", command=self.delete).pack(side="left", padx=4)
        ttk.Button(buttons, text="Clear form", command=self.clear).pack(side="left", padx=4)

        cols = ("id", "name", "dob", "email", "glucose", "hb", "chol", "remarks")
        heads = ("ID", "Full Name", "DOB", "Email", "Glucose", "Haemoglobin", "Cholesterol", "Remarks (AI)")
        widths = (40, 130, 90, 190, 70, 90, 90, 450)
        self.table = ttk.Treeview(self, columns=cols, show="headings")
        for c, h, w in zip(cols, heads, widths):
            self.table.heading(c, text=h)
            self.table.column(c, width=w)
        self.table.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.table.bind("<<TreeviewSelect>>", self.on_select)

        self.refresh()

    def read_form(self):
        return {k: e.get().strip() for k, e in self.entries.items()}

    def refresh(self):
        self.table.delete(*self.table.get_children())
        with db_connect() as db:
            for row in db.execute("SELECT * FROM patients ORDER BY id"):
                self.table.insert("", "end", values=row)

    def clear(self):
        self.selected_id = None
        for e in self.entries.values():
            e.delete(0, "end")

    def on_select(self, _event):
        sel = self.table.selection()
        if not sel:
            return
        row = self.table.item(sel[0])["values"]
        self.selected_id = row[0]
        for (key, _), value in zip(FIELDS, row[1:7]):
            self.entries[key].delete(0, "end")
            self.entries[key].insert(0, value)

    def add(self):
        v, errors = validate(self.read_form())
        if errors:
            messagebox.showerror("Validation error", "\n".join(errors))
            return
        self.config(cursor="watch")
        self.update_idletasks()
        v["remarks"] = get_remarks(v)
        self.config(cursor="")
        with db_connect() as db:
            db.execute("INSERT INTO patients (full_name, dob, email, glucose, haemoglobin, "
                       "cholesterol, remarks) VALUES (:full_name, :dob, :email, :glucose, "
                       ":haemoglobin, :cholesterol, :remarks)", v)
        self.clear()
        self.refresh()

    def update(self):
        if self.selected_id is None:
            messagebox.showinfo("Update", "Select a record from the table first.")
            return
        v, errors = validate(self.read_form(), editing_id=self.selected_id)
        if errors:
            messagebox.showerror("Validation error", "\n".join(errors))
            return
        v["remarks"] = get_remarks(v)
        v["id"] = self.selected_id
        with db_connect() as db:
            db.execute("UPDATE patients SET full_name=:full_name, dob=:dob, email=:email, "
                       "glucose=:glucose, haemoglobin=:haemoglobin, cholesterol=:cholesterol, "
                       "remarks=:remarks WHERE id=:id", v)
        self.clear()
        self.refresh()

    def delete(self):
        if self.selected_id is None:
            messagebox.showinfo("Delete", "Select a record from the table first.")
            return
        if messagebox.askyesno("Delete", "Delete this record?"):
            with db_connect() as db:
                db.execute("DELETE FROM patients WHERE id=?", (self.selected_id,))
            self.clear()
            self.refresh()


if __name__ == "__main__":
    init_db()
    App().mainloop()
