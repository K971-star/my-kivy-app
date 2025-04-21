import os
import shutil
import sqlite3
import re
import bcrypt
import requests  # For checking if the user is online
import yagmail
import fitz  # PyMuPDF for PDF viewing
from email_validator import validate_email, EmailNotValidError
from kivy.app import App
from kivy.uix.screenmanager import ScreenManager, Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.textinput import TextInput
from kivy.uix.scrollview import ScrollView
from kivy.uix.progressbar import ProgressBar
from kivy.clock import Clock
from android.permissions import request_permissions, Permission  # For Android permissions
from jnius import autoclass  # For accessing Android classes

# Request permissions
request_permissions([Permission.READ_EXTERNAL_STORAGE, Permission.WRITE_EXTERNAL_STORAGE])

# Android Classes
PythonActivity = autoclass('org.kivy.android.PythonActivity')
TextToSpeech = autoclass('android.speech.tts.TextToSpeech')
Context = autoclass('android.content.Context')

# Initialize TTS
tts = TextToSpeech(PythonActivity.mActivity, None)


def speak(text):
    if not tts.isSpeaking():
        tts.speak(text, TextToSpeech.QUEUE_FLUSH, None, None)

# Database

def create_database():
    conn = sqlite3.connect('files.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS uploads (
        id INTEGER PRIMARY KEY,
        course TEXT,
        file_path TEXT,
        file_type TEXT,
        upload_date TEXT)''')
    conn.commit()
    conn.close()


def add_file_to_db(course, file_path, file_type):
    conn = sqlite3.connect('files.db')
    c = conn.cursor()
    c.execute("INSERT INTO uploads (course, file_path, file_type, upload_date) VALUES (?, ?, ?, datetime('now'))",
              (course, file_path, file_type))
    conn.commit()
    conn.close()

# Check internet

def is_online():
    try:
        requests.get('http://google.com', timeout=5)
        return True
    except requests.ConnectionError:
        return False

downloaded_files = set()


class MainMenu(Screen):
    def __init__(self, **kwargs):
        super(MainMenu, self).__init__(**kwargs)
        layout = BoxLayout(orientation='vertical', padding=10, spacing=10)

        courses = ['MA 110', 'BI 110', 'CS 110', 'PH 110', 'LA 110', 'CH 110']
        for course in courses:
            btn = Button(text=course)
            btn.bind(on_press=lambda instance, c=course: self.open_course(c))
            layout.add_widget(btn)

        profile_btn = Button(text='Profile')
        profile_btn.bind(on_press=self.open_profile)
        layout.add_widget(profile_btn)

        self.add_widget(layout)

    def open_course(self, course_name):
        self.manager.current = f'{course_name}_screen'

    def open_profile(self, _instance):
        self.manager.current = 'profile'


class CourseScreen(Screen):
    def __init__(self, course_name, **kwargs):
        super(CourseScreen, self).__init__(**kwargs)
        self.course_name = course_name

        layout = BoxLayout(orientation='vertical', padding=10, spacing=10)
        layout.add_widget(Label(text=f"{course_name} Course", font_size=24))

        tutorial_btn = Button(text='Tutorial Sheets')
        tutorial_btn.bind(on_press=lambda instance: self.open_files('tutorial'))
        layout.add_widget(tutorial_btn)

        notes_btn = Button(text='Notes')
        notes_btn.bind(on_press=lambda instance: self.open_files('notes'))
        layout.add_widget(notes_btn)

        exams_btn = Button(text='Sessional Papers')
        exams_btn.bind(on_press=lambda instance: self.open_files('sessional papers'))
        layout.add_widget(exams_btn)

        back_btn = Button(text="Back to Main Menu")
        back_btn.bind(on_press=lambda instance: setattr(self.manager, 'current', 'main_menu'))
        layout.add_widget(back_btn)

        self.add_widget(layout)

    def open_files(self, file_type):
        course_folder = os.path.join(os.getcwd(), 'Notes', self.course_name)
        file_folder = os.path.join(course_folder, file_type)

        if os.path.exists(file_folder):
            files = os.listdir(file_folder)
            if files:
                self.show_files(files, file_folder)
            else:
                self.show_popup("Error", "No files found in the folder!")
        else:
            self.show_popup("Error", "Course folder does not exist!")

    def show_files(self, files, folder_path):
        layout = BoxLayout(orientation='vertical', padding=10, spacing=10, size_hint_y=None)
        layout.bind(minimum_height=layout.setter('height'))

        os.makedirs("app_data", exist_ok=True)

        for file in files:
            if file in downloaded_files:
                file_btn = Button(text=f"Open {file}", size_hint_y=None, height=40)
                file_btn.bind(on_press=lambda instance, f=file: self.show_file_content(f))
            else:
                file_btn = Button(text=f"Download {file}", size_hint_y=None, height=40)
                file_btn.bind(on_press=lambda instance, f=file: self.download_file(f, folder_path))
            layout.add_widget(file_btn)

        scroll_view = ScrollView(size_hint=(1, 1))
        scroll_view.add_widget(layout)

        popup = Popup(title="Available Files", content=scroll_view, size_hint=(0.8, 0.8))
        popup.open()

    def download_file(self, file_name, folder_path):
        if not is_online():
            self.show_popup("No Internet", "You are not connected to the internet. Files can only be downloaded while online.")
            return

        file_url = f'http://your-server.com/{folder_path}/{file_name}'
        target_path = os.path.join("app_data", file_name)
        os.makedirs("app_data", exist_ok=True)

        progress_bar = ProgressBar(max=100)
        popup_layout = BoxLayout(orientation='vertical', spacing=10, padding=10)
        popup_layout.add_widget(Label(text="Downloading..."))
        popup_layout.add_widget(progress_bar)
        download_popup = Popup(title="Download Progress", content=popup_layout, size_hint=(0.8, 0.4))
        download_popup.open()

        def perform_download(dt):
            try:
                response = requests.get(file_url, stream=True)
                total_size = int(response.headers.get('content-length', 0))
                downloaded_size = 0

                with open(target_path, 'wb') as f:
                    for chunk in response.iter_content(1024):
                        if chunk:
                            f.write(chunk)
                            downloaded_size += len(chunk)
                            progress = int((downloaded_size / total_size) * 100)
                            progress_bar.value = progress

                downloaded_files.add(file_name)
                download_popup.dismiss()
                self.show_popup("Download Complete", f"{file_name} downloaded!")
            except Exception as e:
                download_popup.dismiss()
                self.show_popup("Error", f"Failed to download {file_name}: {str(e)}")

        Clock.schedule_once(perform_download)

    def show_file_content(self, file_name):
        file_path = os.path.join("app_data", file_name)
        if file_name.endswith('.pdf'):
            self.open_pdf(file_path)
        else:
            self.show_popup("Error", "Unsupported file format.")

    def open_pdf(self, file_path):
        try:
            document = fitz.open(file_path)
            pdf_text = ""
            for page in document:
                pdf_text += page.get_text()
            document.close()

            pdf_popup = Popup(title="PDF Content", content=Label(text=pdf_text, size_hint=(1, None)), size_hint=(0.9, 0.9))
            pdf_popup.open()
        except Exception as e:
            self.show_popup("Error", f"Failed to open PDF: {str(e)}")

    @staticmethod
    def show_popup(title, message):
        popup = Popup(title=title, content=Label(text=message), size_hint=(0.8, 0.8))
        popup.open()


class MyApp(App):
    def build(self):
        self.title = "Academia Studies"
        sm = ScreenManager()
        sm.add_widget(MainMenu(name="main_menu"))

        sm.add_widget(CourseScreen("MA 110", name="MA 110_screen"))
        sm.add_widget(CourseScreen("BI 110", name="BI 110_screen"))
        sm.add_widget(CourseScreen("CS 110", name="CS 110_screen"))
        sm.add_widget(CourseScreen("PH 110", name="PH 110_screen"))
        sm.add_widget(CourseScreen("LA 110", name="LA 110_screen"))
        sm.add_widget(CourseScreen("CH 110", name="CH 110_screen"))

        return sm

if __name__ == '__main__':
    create_database()
    MyApp().run()
