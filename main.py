import tkinter as tk
from tkinter import ttk, messagebox
import firebase_admin
from firebase_admin import credentials, db
import cv2
import numpy as np
from ultralytics import YOLO
import pytesseract
import re
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import time
from datetime import datetime, timedelta, timezone
import json
import os
import cvzone
import requests
import threading
import uuid


class SmartParkingSystem:
    def __init__(self, root):
        self.root = root
        self.root.title("Smart Parking Management System")
        self.root.geometry("1400x900")
        self.root.configure(bg='#1e3a5f')

        # Make window responsive
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        # Set theme
        self.style = ttk.Style()
        self.style.theme_use('clam')
        self.configure_styles()

        # Initialize Firebase
        self.init_firebase()

        # Load YOLO model for number plate detection
        self.load_model()

        # Initialize variables
        self.current_booking = None
        self.payment_link = None
        self.detection_active = False
        self.last_detected_plate = None
        self.detection_cooldown = 0
        self.parking_data = {
            'slot1': {'status': 'unknown', 'distance': 0, 'carNumber': '', 'carType': ''},
            'slot2': {'status': 'unknown', 'distance': 0, 'carNumber': '', 'carType': ''},
            'slot3': {'status': 'unknown', 'distance': 0, 'carNumber': '', 'carType': ''},
            'slot4': {'status': 'unknown', 'distance': 0, 'carNumber': '', 'carType': ''}
        }

        # Set Tesseract path
        pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

        # Email configuration
        self.smtp_server = "smtp.gmail.com"
        self.smtp_port = 587
        self.sender_email = "sb284160@gmail.com"
        self.sender_password = "almg jghc wvws imli"

        # Payment configuration
        self.payment_base_url = "https://idyllic-choux-9ff643.netlify.app/"

        # Create GUI
        self.create_gui()

        # Start real-time updates
        self.update_display()
        self.start_notification_service()

        # Start booking listener
        self.start_booking_listener()

    def configure_styles(self):
        """Configure modern styles for the application"""
        self.style.configure('Title.TLabel',
                             font=('Arial', 20, 'bold'),
                             background='#1e3a5f',
                             foreground='white')

        self.style.configure('Card.TLabelframe',
                             background='#2d4a6e',
                             foreground='white',
                             borderwidth=2,
                             relief='raised')

        self.style.configure('Card.TLabelframe.Label',
                             background='#2d4a6e',
                             foreground='white',
                             font=('Arial', 11, 'bold'))

        self.style.configure('Success.TButton',
                             background='#28a745',
                             foreground='white',
                             font=('Arial', 10, 'bold'),
                             focuscolor='none')

        self.style.configure('Primary.TButton',
                             background='#007bff',
                             foreground='white',
                             font=('Arial', 10, 'bold'),
                             focuscolor='none')

        self.style.configure('Warning.TButton',
                             background='#ffc107',
                             foreground='black',
                             font=('Arial', 10, 'bold'),
                             focuscolor='none')

        self.style.configure('Info.TButton',
                             background='#17a2b8',
                             foreground='white',
                             font=('Arial', 10, 'bold'),
                             focuscolor='none')

    def init_firebase(self):
        """Initialize Firebase connection"""
        try:
            # Use service account or anonymous auth
            cred = credentials.Certificate("parking-system-firebase-adminsdk.json")
            firebase_admin.initialize_app(cred, {
                'databaseURL': 'https://smart-parking-system-8fdbd-default-rtdb.firebaseio.com/'
            })
            self.db_ref = db.reference()
            print("Firebase initialized successfully")
            self.log_message("Firebase initialized successfully")
        except Exception as e:
            messagebox.showerror("Firebase Error", f"Failed to initialize Firebase: {str(e)}")

    def load_model(self):
        """Load YOLO model for number plate detection"""
        try:
            # Check if model file exists
            if not os.path.exists('best.pt'):
                messagebox.showerror("Model Error", "best.pt model file not found!")
                return

            self.plate_model = YOLO('best.pt')
            print("Number plate detection model loaded successfully")
            self.log_message("Number plate detection model loaded successfully")
        except Exception as e:
            messagebox.showerror("Model Error", f"Failed to load model: {str(e)}")

    def create_gui(self):
        """Create the main GUI interface"""
        # Main container
        main_container = tk.Frame(self.root, bg='#1e3a5f')
        main_container.pack(fill='both', expand=True, padx=15, pady=10)
        main_container.columnconfigure(0, weight=3)
        main_container.columnconfigure(1, weight=2)
        main_container.rowconfigure(1, weight=1)

        # Header
        header_frame = tk.Frame(main_container, bg='#1e3a5f')
        header_frame.grid(row=0, column=0, columnspan=2, sticky='ew', pady=(0, 10))

        title_label = tk.Label(header_frame,
                               text="🚗 SMART PARKING MANAGEMENT SYSTEM",
                               font=('Arial', 20, 'bold'),
                               fg='white',
                               bg='#1e3a5f')
        title_label.pack()

        # Left Frame - Camera and Detection
        left_frame = ttk.LabelFrame(main_container, text="LIVE CAMERA FEED & PLATE DETECTION", padding="10",
                                    style='Card.TLabelframe')
        left_frame.grid(row=1, column=0, sticky='nsew', padx=(0, 10))
        left_frame.columnconfigure(0, weight=1)
        left_frame.rowconfigure(0, weight=1)

        # Camera feed
        camera_container = tk.Frame(left_frame, bg='#34495e', bd=2, relief='sunken')
        camera_container.grid(row=0, column=0, sticky='nsew', padx=5, pady=5)

        self.camera_label = tk.Label(camera_container, text="Camera Initializing...",
                                     bg='black', fg='white', font=('Arial', 10),
                                     width=60, height=15)
        self.camera_label.pack(padx=2, pady=2, fill='both', expand=True)

        # Detection controls
        control_frame = tk.Frame(left_frame, bg='#2d4a6e')
        control_frame.grid(row=1, column=0, sticky='ew', padx=5, pady=5)
        control_frame.columnconfigure(0, weight=1)
        control_frame.columnconfigure(1, weight=1)

        self.detect_btn = ttk.Button(control_frame, text="🎥 START DETECTION",
                                     command=self.toggle_detection, style='Primary.TButton')
        self.detect_btn.grid(row=0, column=0, sticky='ew', padx=(0, 5))

        self.capture_btn = ttk.Button(control_frame, text="📸 CAPTURE & PROCESS",
                                      command=self.capture_and_process, style='Info.TButton')
        self.capture_btn.grid(row=0, column=1, sticky='ew', padx=(5, 0))

        # Detection status
        status_frame = tk.Frame(left_frame, bg='#2d4a6e')
        status_frame.grid(row=2, column=0, sticky='ew', padx=5, pady=(0, 5))

        self.detection_status = tk.Label(status_frame, text="Detection: INACTIVE",
                                         font=('Arial', 10, 'bold'), fg='#dc3545', bg='#2d4a6e')
        self.detection_status.pack()

        # Detection results
        result_frame = ttk.LabelFrame(left_frame, text="DETECTION RESULTS", padding="8",
                                      style='Card.TLabelframe')
        result_frame.grid(row=3, column=0, sticky='ew', padx=5, pady=5)

        plate_info_frame = tk.Frame(result_frame, bg='#2d4a6e')
        plate_info_frame.pack(fill='x', pady=3)

        tk.Label(plate_info_frame, text="Detected Plate:", font=('Arial', 10, 'bold'),
                 fg='white', bg='#2d4a6e', width=15, anchor='w').grid(row=0, column=0, sticky='w', padx=5)
        self.detected_plate_var = tk.StringVar(value="None")
        tk.Label(plate_info_frame, textvariable=self.detected_plate_var, font=('Arial', 10, 'bold'),
                 fg='#f39c12', bg='#2d4a6e', width=15, anchor='w').grid(row=0, column=1, sticky='w', padx=5)

        tk.Label(plate_info_frame, text="Confidence:", font=('Arial', 10, 'bold'),
                 fg='white', bg='#2d4a6e', width=15, anchor='w').grid(row=0, column=2, sticky='w', padx=5)
        self.confidence_var = tk.StringVar(value="0%")
        tk.Label(plate_info_frame, textvariable=self.confidence_var, font=('Arial', 10, 'bold'),
                 fg='#00bc8c', bg='#2d4a6e', width=10, anchor='w').grid(row=0, column=3, sticky='w', padx=5)

        # Vehicle type
        vehicle_type_frame = tk.Frame(result_frame, bg='#2d4a6e')
        vehicle_type_frame.pack(fill='x', pady=3)

        tk.Label(vehicle_type_frame, text="Vehicle Type:", font=('Arial', 10, 'bold'),
                 fg='white', bg='#2d4a6e', width=15, anchor='w').grid(row=0, column=0, sticky='w', padx=5)
        self.vehicle_type_var = tk.StringVar(value="Not Detected")
        tk.Label(vehicle_type_frame, textvariable=self.vehicle_type_var, font=('Arial', 10, 'bold'),
                 fg='#3498db', bg='#2d4a6e', width=25, anchor='w').grid(row=0, column=1, sticky='w', padx=5)

        # Customer Information
        customer_frame = tk.Frame(result_frame, bg='#2d4a6e')
        customer_frame.pack(fill='x', pady=3)

        tk.Label(customer_frame, text="Customer Phone:", font=('Arial', 10, 'bold'),
                 fg='white', bg='#2d4a6e', width=15, anchor='w').grid(row=0, column=0, sticky='w', padx=5)
        self.customer_phone_var = tk.StringVar(value="Not Found")
        tk.Label(customer_frame, textvariable=self.customer_phone_var, font=('Arial', 10, 'bold'),
                 fg='#9b59b6', bg='#2d4a6e', width=15, anchor='w').grid(row=0, column=1, sticky='w', padx=5)

        tk.Label(customer_frame, text="Customer Email:", font=('Arial', 10, 'bold'),
                 fg='white', bg='#2d4a6e', width=15, anchor='w').grid(row=1, column=0, sticky='w', padx=5)
        self.customer_email_var = tk.StringVar(value="Not Found")
        tk.Label(customer_frame, textvariable=self.customer_email_var, font=('Arial', 9),
                 fg='#9b59b6', bg='#2d4a6e', width=25, anchor='w').grid(row=1, column=1, sticky='w', padx=5)

        # OCR results
        ocr_frame = tk.Frame(result_frame, bg='#2d4a6e')
        ocr_frame.pack(fill='x', pady=3)

        tk.Label(ocr_frame, text="OCR Text:", font=('Arial', 10, 'bold'),
                 fg='white', bg='#2d4a6e', width=15, anchor='w').grid(row=0, column=0, sticky='nw', padx=5)
        self.ocr_text_var = tk.StringVar(value="Waiting for detection...")
        tk.Label(ocr_frame, textvariable=self.ocr_text_var, font=('Arial', 9),
                 fg='#e74c3c', bg='#2d4a6e', wraplength=350, justify='left').grid(row=0, column=1, sticky='w', padx=5)

        # Right Frame - Parking Status and Payment
        right_frame = tk.Frame(main_container, bg='#1e3a5f')
        right_frame.grid(row=1, column=1, sticky='nsew')
        right_frame.columnconfigure(0, weight=1)
        right_frame.rowconfigure(0, weight=0)
        right_frame.rowconfigure(1, weight=1)

        # Parking Status
        status_frame = ttk.LabelFrame(right_frame, text="PARKING LOT STATUS", padding="10", style='Card.TLabelframe')
        status_frame.grid(row=0, column=0, sticky='ew', pady=(0, 10))
        status_frame.columnconfigure(0, weight=1)
        status_frame.columnconfigure(1, weight=1)

        self.slots_frame = tk.Frame(status_frame, bg='#2d4a6e')
        self.slots_frame.grid(row=0, column=0, columnspan=2, sticky='ew', pady=5)

        # Create parking slots display
        self.slot_labels = {}
        self.create_parking_slots()

        # Payment Information Frame
        payment_frame = ttk.LabelFrame(right_frame, text="PAYMENT PROCESSING", padding="10", style='Card.TLabelframe')
        payment_frame.grid(row=1, column=0, sticky='nsew')
        payment_frame.columnconfigure(0, weight=1)
        payment_frame.columnconfigure(1, weight=1)

        # Vehicle Information
        vehicle_frame = tk.Frame(payment_frame, bg='#2d4a6e')
        vehicle_frame.grid(row=0, column=0, columnspan=2, sticky='ew', pady=5)

        tk.Label(vehicle_frame, text="Number Plate:", font=('Arial', 10, 'bold'),
                 fg='white', bg='#2d4a6e', width=15, anchor='w').grid(row=0, column=0, sticky='w', padx=5, pady=3)
        self.plate_var = tk.StringVar()
        plate_entry = tk.Entry(vehicle_frame, textvariable=self.plate_var, width=18,
                               font=('Arial', 10), bg='white', fg='#333')
        plate_entry.grid(row=0, column=1, padx=5, pady=3, sticky='w')

        tk.Label(vehicle_frame, text="Vehicle Type:", font=('Arial', 10, 'bold'),
                 fg='white', bg='#2d4a6e', width=15, anchor='w').grid(row=1, column=0, sticky='w', padx=5, pady=3)
        self.vehicle_type_payment_var = tk.StringVar(value="Not Detected")
        vehicle_type_label = tk.Label(vehicle_frame, textvariable=self.vehicle_type_payment_var,
                                      font=('Arial', 10), fg='white', bg='#2d4a6e', width=18, anchor='w')
        vehicle_type_label.grid(row=1, column=1, padx=5, pady=3, sticky='w')

        # Contact Information
        contact_frame = tk.Frame(payment_frame, bg='#2d4a6e')
        contact_frame.grid(row=1, column=0, columnspan=2, sticky='ew', pady=5)

        tk.Label(contact_frame, text="Phone Number:", font=('Arial', 10, 'bold'),
                 fg='white', bg='#2d4a6e', width=15, anchor='w').grid(row=0, column=0, sticky='w', padx=5, pady=3)
        self.phone_var = tk.StringVar()
        phone_entry = tk.Entry(contact_frame, textvariable=self.phone_var, width=18,
                               font=('Arial', 10), bg='white', fg='#333')
        phone_entry.grid(row=0, column=1, padx=5, pady=3, sticky='w')

        tk.Label(contact_frame, text="Email Address:", font=('Arial', 10, 'bold'),
                 fg='white', bg='#2d4a6e', width=15, anchor='w').grid(row=1, column=0, sticky='w', padx=5, pady=3)
        self.email_var = tk.StringVar()
        email_entry = tk.Entry(contact_frame, textvariable=self.email_var, width=18,
                               font=('Arial', 10), bg='white', fg='#333')
        email_entry.grid(row=1, column=1, padx=5, pady=3, sticky='w')

        # Auto-fetch button
        fetch_frame = tk.Frame(payment_frame, bg='#2d4a6e')
        fetch_frame.grid(row=2, column=0, columnspan=2, sticky='ew', pady=5)

        self.fetch_btn = ttk.Button(fetch_frame, text="🔍 FETCH CUSTOMER DATA",
                                    command=self.fetch_customer_data, style='Info.TButton')
        self.fetch_btn.pack(fill='x', pady=3)

        # Price Calculation
        price_frame = tk.Frame(payment_frame, bg='#2d4a6e')
        price_frame.grid(row=3, column=0, columnspan=2, sticky='ew', pady=5)

        price_breakdown = tk.Frame(price_frame, bg='#2d4a6e')
        price_breakdown.pack(fill='x', pady=3)

        tk.Label(price_breakdown, text="Base Price:", font=('Arial', 9),
                 fg='white', bg='#2d4a6e', width=20, anchor='w').grid(row=0, column=0, sticky='w', padx=5)
        self.base_price_var = tk.StringVar(value="₹50")
        tk.Label(price_breakdown, textvariable=self.base_price_var, font=('Arial', 9, 'bold'),
                 fg='white', bg='#2d4a6e', width=10, anchor='e').grid(row=0, column=1, padx=5, sticky='e')

        tk.Label(price_breakdown, text="Vehicle Adjustment:", font=('Arial', 9),
                 fg='white', bg='#2d4a6e', width=20, anchor='w').grid(row=1, column=0, sticky='w', padx=5)
        self.discount_var = tk.StringVar(value="₹0")
        tk.Label(price_breakdown, textvariable=self.discount_var, font=('Arial', 9, 'bold'),
                 fg='#00bc8c', bg='#2d4a6e', width=10, anchor='e').grid(row=1, column=1, padx=5, sticky='e')

        tk.Label(price_breakdown, text="Overtime Charge:", font=('Arial', 9),
                 fg='white', bg='#2d4a6e', width=20, anchor='w').grid(row=2, column=0, sticky='w', padx=5)
        self.overtime_var = tk.StringVar(value="₹0")
        tk.Label(price_breakdown, textvariable=self.overtime_var, font=('Arial', 9, 'bold'),
                 fg='#ff6b6b', bg='#2d4a6e', width=10, anchor='e').grid(row=2, column=1, padx=5, sticky='e')

        # Total amount
        total_frame = tk.Frame(price_frame, bg='#34495e', bd=1, relief='sunken')
        total_frame.pack(fill='x', pady=8, ipady=3)

        tk.Label(total_frame, text="TOTAL AMOUNT:", font=('Arial', 12, 'bold'),
                 fg='white', bg='#34495e').pack(side='left', padx=8)
        self.total_var = tk.StringVar(value="₹50")
        total_label = tk.Label(total_frame, textvariable=self.total_var,
                               font=('Arial', 14, 'bold'), fg='#f39c12', bg='#34495e')
        total_label.pack(side='right', padx=8)

        # Action buttons
        action_frame = tk.Frame(payment_frame, bg='#2d4a6e')
        action_frame.grid(row=4, column=0, columnspan=2, sticky='ew', pady=10)

        self.send_payment_btn = ttk.Button(action_frame, text="📧 SEND PAYMENT LINK",
                                           command=self.send_payment_link, style='Primary.TButton')
        self.send_payment_btn.pack(fill='x', pady=3)

        self.process_payment_btn = ttk.Button(action_frame, text="💳 PROCESS PAYMENT",
                                              command=self.process_payment, style='Success.TButton')
        self.process_payment_btn.pack(fill='x', pady=3)

        # System Log
        log_frame = ttk.LabelFrame(main_container, text="SYSTEM LOG", padding="8", style='Card.TLabelframe')
        log_frame.grid(row=2, column=0, columnspan=2, sticky='ew', pady=(10, 0))
        log_frame.columnconfigure(0, weight=1)

        self.log_text = tk.Text(log_frame, height=5, font=('Consolas', 9),
                                bg='#1c2833', fg='#00ff00', wrap=tk.WORD)
        self.log_text.grid(row=0, column=0, sticky='nsew', padx=5, pady=5)

        scrollbar = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_text.yview)
        scrollbar.grid(row=0, column=1, sticky='ns', pady=5)
        self.log_text.configure(yscrollcommand=scrollbar.set)

        # Initialize camera
        self.cap = cv2.VideoCapture(0)
        if not self.cap.isOpened():
            messagebox.showerror("Camera Error", "Cannot access camera. Please check camera connection.")
        self.update_camera()

    def create_parking_slots(self):
        """Create parking slots display"""
        slot_colors = {
            'available': '#28a745',
            'occupied': '#dc3545',
            'reserved': '#ffc107',
            'unknown': '#6c757d'
        }

        for i in range(1, 5):
            row = 0 if i <= 2 else 1
            col = (i - 1) % 2

            slot_container = tk.Frame(self.slots_frame, bg='#34495e', bd=1, relief='raised')
            slot_container.grid(row=row, column=col, sticky='nsew', padx=5, pady=5, ipadx=5, ipady=5)
            self.slots_frame.columnconfigure(col, weight=1)
            self.slots_frame.rowconfigure(row, weight=1)

            slot_header = tk.Frame(slot_container, bg='#2c3e50')
            slot_header.pack(fill='x')

            slot_label = tk.Label(slot_header, text=f"SLOT {i}", font=('Arial', 10, 'bold'),
                                  fg='white', bg='#2c3e50')
            slot_label.pack(pady=3)

            status_label = tk.Label(slot_container, text="UNKNOWN", font=('Arial', 9, 'bold'),
                                    fg=slot_colors['unknown'], bg='#34495e')
            status_label.pack(pady=2)

            info_label = tk.Label(slot_container, text="", font=('Arial', 8),
                                  fg='#bdc3c7', bg='#34495e')
            info_label.pack(pady=1)

            distance_label = tk.Label(slot_container, text="", font=('Arial', 8),
                                      fg='#95a5a6', bg='#34495e')
            distance_label.pack(pady=1)

            time_label = tk.Label(slot_container, text="", font=('Arial', 7),
                                  fg='#7f8c8d', bg='#34495e')
            time_label.pack(pady=1)

            self.slot_labels[i] = {
                'status': status_label,
                'info': info_label,
                'distance': distance_label,
                'time': time_label,
                'container': slot_container
            }

    def log_message(self, message):
        """Add message to log"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.insert(tk.END, f"[{timestamp}] {message}\n")
        self.log_text.see(tk.END)

    def update_camera(self):
        """Update camera feed"""
        if self.cap.isOpened():
            ret, frame = self.cap.read()
            if ret:
                if self.detection_active:
                    frame = self.detect_number_plates(frame)

                # Convert frame for display
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                frame_resized = cv2.resize(frame_rgb, (640, 480))

                # Convert to PhotoImage
                img = tk.PhotoImage(data=cv2.imencode('.png', frame_resized)[1].tobytes())
                self.camera_label.configure(image=img, text="")
                self.camera_label.image = img
            else:
                self.camera_label.configure(text="Camera Not Available", image="")
        else:
            self.camera_label.configure(text="Camera Not Connected", image="")

        # Update detection cooldown
        if self.detection_cooldown > 0:
            self.detection_cooldown -= 1

        self.root.after(10, self.update_camera)

    def preprocess_for_ocr(self, roi):
        """Apply filters and thresholding to improve OCR accuracy."""
        # Convert to grayscale
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)

        # Apply noise reduction
        gray = cv2.bilateralFilter(gray, 11, 17, 17)

        # Apply adaptive thresholding
        thresh = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY_INV, 35, 15
        )

        # Apply morphological operations to clean up the image
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
        thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)

        # Apply dilation to make characters more connected
        kernel_dilate = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 1))
        thresh = cv2.dilate(thresh, kernel_dilate, iterations=1)

        return thresh

    def get_vehicle_type(self, roi):
        """Estimate vehicle type based on plate background color."""
        try:
            hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
            avg_color = cv2.mean(hsv)[:3]
            h, s, v = avg_color

            if s < 40 and v > 150:
                return "Private (White Plate)"
            elif 20 < h < 40 and s > 100:
                return "Commercial (Yellow Plate)"
            elif 35 < h < 85 and s > 50:
                return "Electric (Green Plate)"
            else:
                return "Private (White Plate)"
        except:
            return "Private (White Plate)"

    def format_number_plate(self, text):
        """Format detected number plate with proper spacing like 'MH 19 EQ 0009'"""
        try:
            # Remove all spaces and special characters
            clean_text = re.sub(r'[^A-Z0-9]', '', text.upper())

            # Check if we have enough characters for a valid plate
            if len(clean_text) < 8:
                return clean_text  # Return as is if too short

            # Indian number plate format: XX XX XX XXXX or similar variations
            # Common patterns:
            # - MH 19 EQ 0009 (10 chars)
            # - DL 01 AB 1234 (10 chars)
            # - KA 05 MN 1234 (10 chars)

            if len(clean_text) == 10:
                # Format: XX 99 XX 9999
                formatted = f"{clean_text[0:2]} {clean_text[2:4]} {clean_text[4:6]} {clean_text[6:10]}"
            elif len(clean_text) == 9:
                # Format: XX 99 X 9999
                formatted = f"{clean_text[0:2]} {clean_text[2:4]} {clean_text[4:5]} {clean_text[5:9]}"
            elif len(clean_text) == 8:
                # Format: XX 99 XX 99
                formatted = f"{clean_text[0:2]} {clean_text[2:4]} {clean_text[4:6]} {clean_text[6:8]}"
            elif len(clean_text) > 10:
                # Take first 10 characters and format
                clean_text = clean_text[:10]
                formatted = f"{clean_text[0:2]} {clean_text[2:4]} {clean_text[4:6]} {clean_text[6:10]}"
            else:
                # For other lengths, try to insert spaces every 2 characters
                formatted = ' '.join([clean_text[i:i + 2] for i in range(0, len(clean_text), 2)])

            return formatted.strip()

        except Exception as e:
            self.log_message(f"Plate formatting error: {str(e)}")
            return text  # Return original text if formatting fails

    def detect_number_plates(self, frame):
        """Detect number plates in frame using YOLO and OCR"""
        try:
            # Run YOLO detection
            results = self.plate_model(frame)

            for result in results:
                boxes = result.boxes
                if boxes is not None and len(boxes) > 0:
                    for box in boxes:
                        confidence = float(box.conf[0])
                        if confidence > 0.5:  # Confidence threshold
                            x1, y1, x2, y2 = map(int, box.xyxy[0])
                            w, h = x2 - x1, y2 - y1

                            # Draw detection rectangle with cvzone
                            cvzone.cornerRect(frame, (x1, y1, w, h), l=9, rt=3)

                            # Extract number plate region with padding
                            padding = 5
                            x1_pad = max(0, x1 - padding)
                            y1_pad = max(0, y1 - padding)
                            x2_pad = min(frame.shape[1], x2 + padding)
                            y2_pad = min(frame.shape[0], y2 + padding)

                            plate_roi = frame[y1_pad:y2_pad, x1_pad:x2_pad]

                            if plate_roi.size > 0:  # Ensure ROI is valid
                                # Preprocess ROI for OCR
                                thresh = self.preprocess_for_ocr(plate_roi)

                                # Try multiple OCR configurations for better accuracy
                                texts = []

                                # Configuration 1: Standard
                                text1 = pytesseract.image_to_string(
                                    thresh,
                                    config='--psm 8 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
                                ).strip().replace(" ", "")

                                # Configuration 2: Single line
                                text2 = pytesseract.image_to_string(
                                    thresh,
                                    config='--psm 7 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
                                ).strip().replace(" ", "")

                                # Configuration 3: Single word
                                text3 = pytesseract.image_to_string(
                                    thresh,
                                    config='--psm 13 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
                                ).strip().replace(" ", "")

                                # Add all non-empty results
                                for text in [text1, text2, text3]:
                                    if text and len(text) >= 6:  # Minimum reasonable plate length
                                        texts.append(text)

                                # Choose the best text (longest one usually)
                                if texts:
                                    text = max(texts, key=len)

                                    # Format the number plate with proper spacing
                                    formatted_text = self.format_number_plate(text)

                                    # Detect vehicle type based on plate color
                                    vehicle_type = self.get_vehicle_type(plate_roi)

                                    if formatted_text and self.detection_cooldown == 0:
                                        # Display info on frame
                                        cvzone.putTextRect(frame, f"Plate: {formatted_text}", (x1, y1 - 60),
                                                           scale=2, thickness=2, colorR=(0, 255, 0))
                                        cvzone.putTextRect(frame, f"Type: {vehicle_type}", (x1, y1 - 25),
                                                           scale=2, thickness=2, colorR=(255, 255, 0))

                                        # Update GUI with detection results
                                        self.update_detection_display(formatted_text, confidence, vehicle_type)

                                        # Process the detected vehicle
                                        self.process_detected_vehicle(formatted_text, vehicle_type)

                                        # Set cooldown to prevent multiple detections
                                        self.detection_cooldown = 30  # 30 frames cooldown
                                        self.last_detected_plate = formatted_text

            return frame
        except Exception as e:
            self.log_message(f"Detection error: {str(e)}")
            return frame

    def update_detection_display(self, number_plate, confidence, vehicle_type):
        """Update the detection results display"""
        self.detected_plate_var.set(number_plate)
        self.confidence_var.set(f"{confidence * 100:.1f}%")
        self.vehicle_type_var.set(vehicle_type)
        self.ocr_text_var.set(f"Detected: {number_plate} | Type: {vehicle_type}")

        # Also update the main plate variable for payment processing
        self.plate_var.set(number_plate)
        self.vehicle_type_payment_var.set(vehicle_type)

    def fetch_customer_data(self):
        """Fetch customer data from Firebase based on detected plate"""
        try:
            number_plate = self.plate_var.get()
            if not number_plate:
                messagebox.showwarning("Warning", "Please detect a number plate first")
                return

            self.log_message(f"Fetching customer data for: {number_plate}")

            # Search in bookings
            bookings_ref = self.db_ref.child('bookings')
            bookings = bookings_ref.get()

            customer_found = False

            if bookings:
                for booking_id, booking_data in bookings.items():
                    # Remove spaces for comparison since stored data might not have spaces
                    stored_plate = booking_data.get('carNumber', '').replace(' ', '')
                    current_plate = number_plate.replace(' ', '')

                    if (stored_plate == current_plate and
                            booking_data.get('status') == 'active'):
                        # Found customer data
                        phone = booking_data.get('phone', '')
                        email = booking_data.get('email', '')

                        # Update GUI
                        self.phone_var.set(phone)
                        self.email_var.set(email)
                        self.customer_phone_var.set(phone if phone else "Not Found")
                        self.customer_email_var.set(email if email else "Not Found")

                        self.current_booking = booking_data
                        self.current_booking['id'] = booking_id

                        customer_found = True
                        self.log_message(f"Customer data found: Phone: {phone}, Email: {email}")

                        # Auto-calculate price
                        self.calculate_price()

                        # Auto-send payment link
                        self.root.after(2000, self.send_payment_link)
                        break

            if not customer_found:
                self.log_message("No customer data found for this vehicle")
                self.customer_phone_var.set("Not Found")
                self.customer_email_var.set("Not Found")
                messagebox.showinfo("Info", "No customer data found for this vehicle number")

        except Exception as e:
            self.log_message(f"Error fetching customer data: {str(e)}")
            messagebox.showerror("Error", f"Failed to fetch customer data: {str(e)}")

    def process_detected_vehicle(self, number_plate, vehicle_type):
        """Process detected vehicle and automatically fetch customer data"""
        try:
            # Update display with detection results
            self.plate_var.set(number_plate)
            self.vehicle_type_payment_var.set(vehicle_type)

            self.log_message(f"Vehicle detected: {number_plate} - Type: {vehicle_type}")

            # Automatically fetch customer data
            self.fetch_customer_data()

        except Exception as e:
            self.log_message(f"Vehicle processing error: {str(e)}")

    def capture_and_process(self):
        """Capture image and process for number plate"""
        ret, frame = self.cap.read()
        if ret:
            # Detect number plate
            results = self.plate_model(frame)
            number_plate = None
            vehicle_type = "Not Detected"
            confidence = 0

            for result in results:
                boxes = result.boxes
                if boxes is not None and len(boxes) > 0:
                    for box in boxes:
                        if float(box.conf[0]) > 0.5:
                            x1, y1, x2, y2 = map(int, box.xyxy[0])
                            # Add padding for better OCR
                            padding = 10
                            x1_pad = max(0, x1 - padding)
                            y1_pad = max(0, y1 - padding)
                            x2_pad = min(frame.shape[1], x2 + padding)
                            y2_pad = min(frame.shape[0], y2 + padding)

                            plate_roi = frame[y1_pad:y2_pad, x1_pad:x2_pad]
                            if plate_roi.size > 0:
                                # Preprocess and extract text
                                thresh = self.preprocess_for_ocr(plate_roi)

                                # Try multiple OCR configurations
                                texts = []
                                configs = [
                                    '--psm 8 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789',
                                    '--psm 7 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789',
                                    '--psm 13 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
                                ]

                                for config in configs:
                                    text = pytesseract.image_to_string(thresh, config=config).strip().replace(" ", "")
                                    if text and len(text) >= 6:
                                        texts.append(text)

                                if texts:
                                    # Choose the best text
                                    best_text = max(texts, key=len)
                                    number_plate = self.format_number_plate(best_text)
                                    vehicle_type = self.get_vehicle_type(plate_roi)
                                    confidence = float(box.conf[0])
                                break

            if number_plate:
                self.plate_var.set(number_plate)
                self.vehicle_type_payment_var.set(vehicle_type)
                self.update_detection_display(number_plate, confidence, vehicle_type)
                self.process_detected_vehicle(number_plate, vehicle_type)
                self.log_message(f"Manual capture: {number_plate} - Type: {vehicle_type} - Conf: {confidence:.2f}")
            else:
                messagebox.showwarning("Detection", "No number plate detected in capture")

    def toggle_detection(self):
        """Toggle automatic detection"""
        self.detection_active = not self.detection_active
        if self.detection_active:
            self.detect_btn.config(text="🛑 STOP DETECTION")
            self.detection_status.config(text="Detection: ACTIVE", fg='#28a745')
            self.log_message("Automatic number plate detection started")
        else:
            self.detect_btn.config(text="🎥 START DETECTION")
            self.detection_status.config(text="Detection: INACTIVE", fg='#dc3545')
            self.log_message("Automatic detection stopped")

    def calculate_price(self):
        """Calculate parking price based on vehicle type and overtime"""
        try:
            base_price = 50  # ₹50 base price
            number_plate = self.plate_var.get()
            vehicle_type = self.vehicle_type_payment_var.get()

            # Calculate price modifiers based on vehicle type
            discount = 0
            overtime_charge = 0

            # Vehicle type based pricing
            if "Electric" in vehicle_type:
                discount = base_price * 0.20  # 20% discount for EV
            elif "Commercial" in vehicle_type:
                discount = -base_price * 0.10  # 10% extra for commercial
            # Private vehicles get normal price (discount = 0)

            # Check for overtime if it's an existing booking
            if self.current_booking:
                booked_until_str = self.current_booking.get('bookedUntil')
                if booked_until_str:
                    try:
                        # FIXED: Handle timezone-aware datetime comparison
                        booked_until = datetime.fromisoformat(booked_until_str.replace('Z', '+00:00'))
                        current_time = datetime.now(timezone.utc)

                        # Make both timezone-aware for comparison
                        if booked_until.tzinfo is None:
                            booked_until = booked_until.replace(tzinfo=timezone.utc)

                        if current_time > booked_until:
                            overtime_hours = (current_time - booked_until).total_seconds() / 3600
                            overtime_charge = max(overtime_hours * 25, 0)  # ₹25 per hour overtime
                    except Exception as e:
                        self.log_message(f"Overtime calculation error: {str(e)}")

            total_amount = base_price - discount + overtime_charge

            # Update display
            self.base_price_var.set(f"₹{base_price}")
            self.discount_var.set(f"₹{discount:.2f}")
            self.overtime_var.set(f"₹{overtime_charge:.2f}")
            self.total_var.set(f"₹{total_amount:.2f}")

            self.log_message(
                f"Price calculated: ₹{total_amount:.2f} (Base: ₹{base_price}, Discount: ₹{discount:.2f}, Overtime: ₹{overtime_charge:.2f})")

        except Exception as e:
            self.log_message(f"Price calculation error: {str(e)}")

    def generate_payment_data(self):
        """Generate payment data and store in Firebase"""
        try:
            number_plate = self.plate_var.get()
            vehicle_type = self.vehicle_type_payment_var.get()
            total_amount = self.total_var.get().replace('₹', '')

            # Generate unique payment ID
            payment_id = f"PAY{int(time.time())}"

            # Create payment data
            payment_data = {
                'paymentId': payment_id,
                'vehicleNumber': number_plate,
                'vehicleType': vehicle_type,
                'amount': total_amount,
                'status': 'pending',
                'timestamp': datetime.now().isoformat(),
                'bookingId': self.current_booking['id'] if self.current_booking else None,
                'customerPhone': self.phone_var.get(),
                'customerEmail': self.email_var.get()
            }

            # Store in Firebase
            self.db_ref.child(f'pendingPayments/{payment_id}').set(payment_data)

            self.log_message(f"Payment data generated: {payment_id}")
            return payment_id

        except Exception as e:
            self.log_message(f"Payment data generation error: {str(e)}")
            return None

    def send_payment_link(self):
        """Send payment link via SMS and email"""
        try:
            number_plate = self.plate_var.get()
            phone = self.phone_var.get()
            email = self.email_var.get()
            total_amount = self.total_var.get()
            vehicle_type = self.vehicle_type_payment_var.get()

            if not number_plate:
                messagebox.showerror("Error", "Please detect a number plate first")
                return

            if not email:
                messagebox.showwarning("Warning", "No email address found. Please fetch customer data first.")
                return

            # Generate payment data and get payment ID
            payment_id = self.generate_payment_data()
            if not payment_id:
                raise Exception("Failed to generate payment data")

            # Generate payment link with Netlify URL
            payment_link = f"{self.payment_base_url}/?paymentId={payment_id}&vehicle={number_plate}&amount={total_amount.replace('₹', '')}&type={vehicle_type.split()[0]}"
            self.payment_link = payment_link

            # Send SMS (simulated)
            if phone:
                sms_message = f"Parking Payment: Vehicle {number_plate} ({vehicle_type}). Amount: {total_amount}. Pay here: {payment_link}"
                self.send_sms(phone, sms_message)
            else:
                self.log_message("SMS skipped - no phone number available")

            # Send Email
            email_subject = "Parking Payment Request"
            email_body = f"""
            Dear Customer,

            Your parking payment for vehicle {number_plate} is ready.

            Vehicle Details:
            - Number Plate: {number_plate}
            - Vehicle Type: {vehicle_type}
            - Total Amount: {total_amount}

            Please click the link below to complete your payment:
            {payment_link}

            Price Breakdown:
            - Base Price: {self.base_price_var.get()}
            - Vehicle Type Adjustment: {self.discount_var.get()}
            - Overtime Charge: {self.overtime_var.get()}
            - Total Amount: {total_amount}

            Payment ID: {payment_id}

            Thank you for using our Smart Parking System.

            Best regards,
            Parking Management Team
            """

            self.send_email(email, email_subject, email_body)

            self.log_message(f"Payment link sent to {email} and {phone}")
            messagebox.showinfo("Success", f"Payment link sent successfully!\nEmail: {email}\nPhone: {phone}")

        except Exception as e:
            self.log_message(f"Payment link error: {str(e)}")
            messagebox.showerror("Error", f"Failed to send payment link: {str(e)}")

    def send_sms(self, phone, message):
        """Send SMS notification (simulated)"""
        if phone:
            self.log_message(f"SMS sent to {phone}: {message}")

            # Update Firebase with SMS status
            try:
                self.db_ref.child('system').update({
                    'lastSMS': f"SMS sent to {phone}",
                    'lastSMSTime': datetime.now().isoformat()
                })
            except Exception as e:
                self.log_message(f"SMS logging error: {str(e)}")
        else:
            self.log_message("SMS skipped - no phone number provided")

    def send_email(self, email, subject, body):
        """Send email notification"""
        try:
            if not email:
                self.log_message("Email skipped - no email address provided")
                return

            # Create message
            msg = MIMEMultipart()
            msg['From'] = self.sender_email
            msg['To'] = email
            msg['Subject'] = subject

            msg.attach(MIMEText(body, 'plain'))

            # Send email
            server = smtplib.SMTP(self.smtp_server, self.smtp_port)
            server.starttls()
            server.login(self.sender_email, self.sender_password)
            server.send_message(msg)
            server.quit()

            self.log_message(f"Email sent successfully to {email}")

        except Exception as e:
            self.log_message(f"Email error: {str(e)}")

    def delete_customer_and_vehicle_data(self, booking_id, slot_id, number_plate):
        """Delete customer and vehicle data from Firebase after payment"""
        try:
            self.log_message(f"Starting data cleanup for vehicle: {number_plate}")

            # 1. Delete the booking
            if booking_id:
                self.db_ref.child(f'bookings/{booking_id}').delete()
                self.log_message(f"Deleted booking: {booking_id}")

            # 2. Clear parking slot data
            if slot_id:
                slot_ref = self.db_ref.child(f'parkingSlots/{slot_id}')
                slot_ref.update({
                    'status': 'available',
                    'bookedUntil': None,
                    'bookingId': None,
                    'carNumber': None,
                    'carType': None,
                    'distance': 0
                })
                self.log_message(f"Cleared parking slot: {slot_id}")

            # 3. Delete from pending payments if exists
            pending_payments_ref = self.db_ref.child('pendingPayments')
            pending_payments = pending_payments_ref.get()

            if pending_payments:
                for pay_id, pay_data in pending_payments.items():
                    if (pay_data and
                            pay_data.get('vehicleNumber') == number_plate and
                            pay_data.get('status') == 'pending'):
                        self.db_ref.child(f'pendingPayments/{pay_id}').delete()
                        self.log_message(f"Deleted pending payment: {pay_id}")

            # 4. Delete from active vehicles if exists
            active_vehicles_ref = self.db_ref.child('activeVehicles')
            active_vehicles = active_vehicles_ref.get()

            if active_vehicles:
                for vehicle_id, vehicle_data in active_vehicles.items():
                    if vehicle_data and vehicle_data.get('carNumber') == number_plate:
                        self.db_ref.child(f'activeVehicles/{vehicle_id}').delete()
                        self.log_message(f"Deleted active vehicle: {vehicle_id}")

            # 5. Delete from detected plates if exists
            detected_plates_ref = self.db_ref.child('detectedPlates')
            detected_plates = detected_plates_ref.get()

            if detected_plates:
                for plate_id, plate_data in detected_plates.items():
                    if plate_data and plate_data.get('plateNumber') == number_plate:
                        self.db_ref.child(f'detectedPlates/{plate_id}').delete()
                        self.log_message(f"Deleted detected plate: {plate_id}")

            self.log_message(f"Successfully cleaned up all data for vehicle: {number_plate}")

        except Exception as e:
            self.log_message(f"Error during data cleanup: {str(e)}")

    def process_payment(self):
        """Process payment and update system"""
        try:
            number_plate = self.plate_var.get()
            if not number_plate:
                messagebox.showerror("Error", "No number plate detected")
                return

            # Check if payment was already made via web
            payment_status = self.check_payment_status()
            if payment_status == 'completed':
                messagebox.showinfo("Info", "Payment already processed via web")
                self.delete_customer_data()
                return

            # Simulate payment processing
            payment_id = f"PAY{int(time.time())}"
            booking_id = None
            slot_id = None

            if self.current_booking:
                booking_id = self.current_booking['id']
                slot_id = self.current_booking.get('slot')

                # Update existing booking
                booking_ref = self.db_ref.child(f"bookings/{booking_id}")
                booking_ref.update({
                    'status': 'completed',
                    'paymentId': payment_id,
                    'paymentTime': datetime.now().isoformat(),
                    'amount': self.total_var.get(),
                    'paymentStatus': 'paid',
                    'vehicleType': self.vehicle_type_payment_var.get()
                })

            # Create payment record
            payment_ref = self.db_ref.child(f"payments/{payment_id}")
            payment_ref.set({
                'vehicleNumber': number_plate,
                'vehicleType': self.vehicle_type_payment_var.get(),
                'amount': self.total_var.get(),
                'paymentTime': datetime.now().isoformat(),
                'status': 'completed',
                'bookingId': booking_id,
                'slotId': slot_id,
                'paymentMethod': 'manual'
            })

            # Delete customer and vehicle data
            if booking_id or slot_id:
                self.delete_customer_and_vehicle_data(booking_id, slot_id, number_plate)

            # Send confirmation
            confirmation_msg = f"Payment successful! Vehicle {number_plate} ({self.vehicle_type_payment_var.get()}) can now exit. Payment ID: {payment_id}"

            if self.phone_var.get():
                self.send_sms(self.phone_var.get(), confirmation_msg)

            if self.email_var.get():
                self.send_email(self.email_var.get(), "Payment Confirmation", confirmation_msg)

            # Clear local data
            self.delete_customer_data()

            self.log_message(f"Payment processed successfully: {payment_id}")
            messagebox.showinfo("Success",
                                "Payment processed successfully!\nCustomer data cleared and deleted from system.")

        except Exception as e:
            self.log_message(f"Payment processing error: {str(e)}")
            messagebox.showerror("Error", f"Payment failed: {str(e)}")

    def check_payment_status(self):
        """Check if payment was already made via web"""
        try:
            if not self.current_booking:
                return 'pending'

            booking_ref = self.db_ref.child(f"bookings/{self.current_booking['id']}")
            booking_data = booking_ref.get()

            if booking_data and booking_data.get('paymentStatus') == 'paid':
                return 'completed'
            return 'pending'
        except:
            return 'pending'

    def delete_customer_data(self):
        """Delete customer data from local GUI after payment"""
        try:
            # Clear all form fields
            self.plate_var.set("")
            self.vehicle_type_payment_var.set("Not Detected")
            self.phone_var.set("")
            self.email_var.set("")

            # Reset detection display
            self.detected_plate_var.set("None")
            self.confidence_var.set("0%")
            self.vehicle_type_var.set("Not Detected")
            self.ocr_text_var.set("Waiting for detection...")
            self.customer_phone_var.set("Not Found")
            self.customer_email_var.set("Not Found")

            # Reset price display
            self.base_price_var.set("₹50")
            self.discount_var.set("₹0")
            self.overtime_var.set("₹0")
            self.total_var.set("₹50")

            # Clear current booking
            self.current_booking = None
            self.payment_link = None
            self.last_detected_plate = None

            self.log_message("Local customer data cleared successfully")

        except Exception as e:
            self.log_message(f"Local data clearance error: {str(e)}")

    def update_display(self):
        """Update parking slots display from Firebase"""
        try:
            slots_ref = self.db_ref.child('parkingSlots')
            slots = slots_ref.get()

            if slots:
                for slot_id, slot_data in slots.items():
                    slot_num = int(slot_id.replace('slot', ''))
                    status = slot_data.get('status', 'unknown')
                    car_number = slot_data.get('carNumber', '')
                    car_type = slot_data.get('carType', '')
                    distance = slot_data.get('distance', 0)
                    booked_until = slot_data.get('bookedUntil', '')

                    # Update local data
                    self.parking_data[slot_id] = {
                        'status': status,
                        'carNumber': car_number,
                        'carType': car_type,
                        'distance': distance,
                        'bookedUntil': booked_until
                    }

                    # Update slot display
                    label_info = self.slot_labels[slot_num]

                    # Update status with color coding
                    status_colors = {
                        'available': '#28a745',
                        'occupied': '#dc3545',
                        'reserved': '#ffc107',
                        'unknown': '#6c757d'
                    }

                    status_text = status.upper()
                    label_info['status'].config(
                        text=status_text,
                        fg=status_colors.get(status, '#6c757d')
                    )

                    # Update info text
                    if status == 'occupied':
                        info_text = f"Car: {car_number}" if car_number else "Occupied"
                        type_text = f"Type: {car_type}" if car_type else ""
                    elif status == 'reserved':
                        info_text = f"Reserved: {car_number}" if car_number else "Reserved"
                        type_text = f"Type: {car_type}" if car_type else ""
                    else:
                        info_text = "Available" if status == 'available' else "Unknown"
                        type_text = ""

                    label_info['info'].config(text=info_text)

                    # Update distance
                    distance_text = f"Dist: {distance}cm" if distance > 0 else ""
                    label_info['distance'].config(text=distance_text)

                    # Update time information
                    time_text = ""
                    if booked_until and status in ['reserved', 'occupied']:
                        try:
                            # FIXED: Handle timezone-aware datetime comparison
                            booked_time = datetime.fromisoformat(booked_until.replace('Z', '+00:00'))
                            current_time = datetime.now(timezone.utc)

                            # Make both timezone-aware for comparison
                            if booked_time.tzinfo is None:
                                booked_time = booked_time.replace(tzinfo=timezone.utc)

                            time_diff = booked_time - current_time

                            if time_diff.total_seconds() > 0:
                                hours = int(time_diff.total_seconds() // 3600)
                                minutes = int((time_diff.total_seconds() % 3600) // 60)
                                time_text = f"Time left: {hours}h {minutes}m"
                            else:
                                time_text = "TIME EXPIRED"
                        except Exception as e:
                            time_text = "Time error"

                    label_info['time'].config(text=time_text)

        except Exception as e:
            self.log_message(f"Display update error: {str(e)}")

        # Schedule next update
        self.root.after(3000, self.update_display)

    def start_booking_listener(self):
        """Start listening for new bookings and send email notifications"""

        def booking_listener_worker():
            last_checked = datetime.now()
            while True:
                try:
                    # Check for new bookings created since last check
                    bookings_ref = self.db_ref.child('bookings')
                    bookings = bookings_ref.get()

                    if bookings:
                        for booking_id, booking_data in bookings.items():
                            if booking_data:
                                # Check if this is a new booking
                                booking_time_str = booking_data.get('timestamp')
                                if booking_time_str:
                                    try:
                                        booking_time = datetime.fromisoformat(booking_time_str.replace('Z', '+00:00'))
                                        if booking_time > last_checked:
                                            # New booking found - send notification
                                            self.send_booking_confirmation(booking_data)
                                    except:
                                        pass

                    # Update last checked time
                    last_checked = datetime.now()
                    time.sleep(10)  # Check every 10 seconds

                except Exception as e:
                    self.log_message(f"Booking listener error: {str(e)}")
                    time.sleep(30)

        # Start booking listener thread
        booking_thread = threading.Thread(target=booking_listener_worker, daemon=True)
        booking_thread.start()

    def send_booking_confirmation(self, booking_data):
        """Send booking confirmation email"""
        try:
            car_number = booking_data.get('carNumber', '')
            slot = booking_data.get('slot', '')
            duration = booking_data.get('duration', '')
            email = booking_data.get('email', '')
            phone = booking_data.get('phone', '')
            booked_until = booking_data.get('bookedUntil', '')

            if email:
                subject = "Parking Booking Confirmation"
                body = f"""
                Dear Customer,

                Your parking booking has been confirmed!

                Booking Details:
                - Vehicle Number: {car_number}
                - Parking Slot: {slot}
                - Duration: {duration}
                - Booked Until: {booked_until}
                - Booking Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

                Please arrive within your booked time slot.

                Thank you for choosing our Smart Parking System.

                Best regards,
                Parking Management Team
                """

                self.send_email(email, subject, body)
                self.log_message(f"Booking confirmation sent to {email} for vehicle {car_number}")

            if phone:
                sms_message = f"Booking confirmed! Vehicle {car_number}, Slot {slot}, Valid until {booked_until}. Thank you!"
                self.send_sms(phone, sms_message)

        except Exception as e:
            self.log_message(f"Booking confirmation error: {str(e)}")

    def start_notification_service(self):
        """Start background service for sending notifications"""

        def notification_worker():
            while True:
                try:
                    self.check_and_send_notifications()
                    time.sleep(300)  # Check every 5 minutes
                except Exception as e:
                    self.log_message(f"Notification error: {str(e)}")
                    time.sleep(60)

        # Start notification thread
        notification_thread = threading.Thread(target=notification_worker, daemon=True)
        notification_thread.start()

    def check_and_send_notifications(self):
        """Check for upcoming expirations and send notifications every 5 minutes"""
        try:
            bookings_ref = self.db_ref.child('bookings')
            bookings = bookings_ref.get()

            if not bookings:
                return

            current_time = datetime.now(timezone.utc)

            for booking_id, booking_data in bookings.items():
                if booking_data and booking_data.get('status') == 'active':
                    booked_until_str = booking_data.get('bookedUntil')
                    if not booked_until_str:
                        continue

                    try:
                        # FIXED: Handle timezone-aware datetime comparison
                        booked_until = datetime.fromisoformat(booked_until_str.replace('Z', '+00:00'))

                        # Make both timezone-aware for comparison
                        if booked_until.tzinfo is None:
                            booked_until = booked_until.replace(tzinfo=timezone.utc)

                        time_diff = booked_until - current_time

                        # Send notification for any remaining time (every 5 minutes)
                        if time_diff.total_seconds() > 0:
                            car_number = booking_data.get('carNumber', '')
                            phone = booking_data.get('phone', '')
                            email = booking_data.get('email', '')

                            hours_left = int(time_diff.total_seconds() // 3600)
                            minutes_left = int((time_diff.total_seconds() % 3600) // 60)

                            # Format time left message
                            if hours_left > 0:
                                time_left_msg = f"{hours_left} hours and {minutes_left} minutes"
                            else:
                                time_left_msg = f"{minutes_left} minutes"

                            message = f"Reminder: Your parking time for {car_number} expires in {time_left_msg}. Please extend your booking if needed."

                            # Send notification regardless of time left (every 5 minutes check)
                            if phone:
                                self.send_sms(phone, message)

                            if email:
                                self.send_email(email, "Parking Time Reminder", message)

                            self.log_message(f"Reminder sent for {car_number} - {time_left_msg} left")

                    except Exception as e:
                        self.log_message(f"Notification processing error: {str(e)}")

        except Exception as e:
            self.log_message(f"Notification check error: {str(e)}")

    def __del__(self):
        """Cleanup resources"""
        if hasattr(self, 'cap') and self.cap.isOpened():
            self.cap.release()


def main():
    root = tk.Tk()
    app = SmartParkingSystem(root)
    root.mainloop()


if __name__ == "__main__":
    main()