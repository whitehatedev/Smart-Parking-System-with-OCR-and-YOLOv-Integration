#include <WiFi.h>
#include <Firebase_ESP_Client.h>
#include <addons/TokenHelper.h>
#include <HardwareSerial.h>
#include <time.h>

// WiFi credentials
#define WIFI_SSID ""
#define WIFI_PASSWORD ""

// Firebase configuration
#define API_KEY "AIzaSyDxylltNCIocdn_6w_XRKp2GOOBwMLieDY"
#define DATABASE_URL "https://smart-parking-system-8fdbd-default-rtdb.firebaseio.com"

// User credentials for Firebase authentication
#define USER_EMAIL ""
#define USER_PASSWORD ""

// Ultrasonic sensor pins
#define TRIG_PIN_1 2
#define ECHO_PIN_1 4
#define TRIG_PIN_2 5
#define ECHO_PIN_2 18
#define TRIG_PIN_3 19
#define ECHO_PIN_3 21
#define TRIG_PIN_4 22
#define ECHO_PIN_4 23

// GSM Module connections (SIM800L)
#define GSM_RX 16
#define GSM_TX 17
#define GSM_POWER 27

// LED indicators
#define LED_GREEN 32
#define LED_RED 33
#define LED_BLUE 34

// Parking slot thresholds (in cm)
#define EMPTY_DISTANCE 20
#define OCCUPIED_DISTANCE 10  

// Define Firebase objects
FirebaseData fbdo;
FirebaseAuth auth;
FirebaseConfig config;

// GSM Serial
HardwareSerial gsmSerial(2);

unsigned long sendDataPrevMillis = 0;
unsigned long checkBookingsPrevMillis = 0;
unsigned long checkPaymentsPrevMillis = 0;
bool signupOK = false;
bool gsmReady = false;

struct BookingInfo {
  String slotId;
  String phoneNumber;
  String carNumber;
  String endTime;
  float amountDue;
  bool paymentPending;
};

BookingInfo currentBookings[4];
int bookingCount = 0;

// ============ MISSING FUNCTION IMPLEMENTATIONS ============

String sendATCommand(String command, unsigned long timeout) {
  String response = "";
  gsmSerial.println(command);
  unsigned long startTime = millis();
  
  while (millis() - startTime < timeout) {
    if (gsmSerial.available()) {
      response += gsmSerial.readString();
    }
  }
  
  Serial.println("GSM Response: " + response);
  return response;
}

void sendSMS(String phoneNumber, String message) {
  if (!gsmReady) {
    Serial.println("GSM not ready, cannot send SMS");
    return;
  }
  
  Serial.println("Sending SMS to: " + phoneNumber);
  Serial.println("Message: " + message);
  
  gsmSerial.println("AT+CMGS=\"" + phoneNumber + "\"");
  delay(1000);
  gsmSerial.print(message);
  delay(500);
  gsmSerial.write(26);  // Ctrl+Z to send
  delay(5000);
  
  Serial.println("SMS sent successfully");
}

void handleGSMResponse() {
  if (gsmSerial.available()) {
    String response = gsmSerial.readString();
    Serial.println("GSM Received: " + response);
  }
}

int readUltrasonic(int trigPin, int echoPin) {
  digitalWrite(trigPin, LOW);
  delayMicroseconds(2);
  digitalWrite(trigPin, HIGH);
  delayMicroseconds(10);
  digitalWrite(trigPin, LOW);
  
  long duration = pulseIn(echoPin, HIGH);
  int distance = duration * 0.034 / 2;
  
  // Filter out unrealistic values
  if (distance > 300 || distance < 2) {
    return -1; // Error value
  }
  
  return distance;
}

String determineStatus(int distance) {
  if (distance == -1) {
    return "unknown";
  } else if (distance <= OCCUPIED_DISTANCE) {
    return "occupied";
  } else if (distance >= EMPTY_DISTANCE) {
    return "available";
  } else {
    return "unknown"; // In between values
  }
}

void updateFirebaseSlot(String slotId, String status, int distance) {
  String path = "parkingSlots/" + slotId;
  
  FirebaseJson json;
  json.set("status", status);
  json.set("distance", distance);
  json.set("lastUpdated", millis());
  
  if (Firebase.RTDB.setJSON(&fbdo, path.c_str(), &json)) {
    Serial.println("Updated " + slotId + " in Firebase");
  } else {
    Serial.println("Failed to update " + slotId);
    Serial.println("Reason: " + fbdo.errorReason());
  }
}

time_t parseISO8601(String isoTime) {
  // Simple ISO 8601 parser (YYYY-MM-DDTHH:MM:SS)
  struct tm tm;
  memset(&tm, 0, sizeof(tm));
  
  // Parse the ISO 8601 string
  int year, month, day, hour, minute, second;
  sscanf(isoTime.c_str(), "%d-%d-%dT%d:%d:%d", 
         &year, &month, &day, &hour, &minute, &second);
  
  tm.tm_year = year - 1900;
  tm.tm_mon = month - 1;
  tm.tm_mday = day;
  tm.tm_hour = hour;
  tm.tm_min = minute;
  tm.tm_sec = second;
  tm.tm_isdst = -1;
  
  return mktime(&tm);
}

time_t getCurrentTime() {
  // For ESP32, you can use NTP to get real time
  // For now, using millis() as a simple solution
  // In production, use NTP: configTime(gmtOffset_sec, daylightOffset_sec, ntpServer);
  return millis() / 1000; // Convert to seconds (simplified)
}

void initializeBookings() {
  // Clear current bookings
  for (int i = 0; i < 4; i++) {
    currentBookings[i] = {"", "", "", "", 0.0, false};
  }
  bookingCount = 0;
  
  // Load existing bookings from Firebase
  loadExistingBookings();
}

void loadExistingBookings() {
  String path = "bookings";
  
  if (Firebase.RTDB.getJSON(&fbdo, path.c_str())) {
    FirebaseJson *json = fbdo.jsonObjectPtr();
    FirebaseJsonData result;
    
    // Check each slot for active bookings
    for (int i = 1; i <= 4; i++) {
      String slotPath = "slot" + String(i);
      if (json->get(result, slotPath + "/phone")) {
        String phone = result.stringValue;
        
        // Get other booking details
        String carNumber = "";
        String endTime = "";
        
        if (json->get(result, slotPath + "/carNumber")) {
          carNumber = result.stringValue;
        }
        
        if (json->get(result, slotPath + "/bookedUntil")) {
          endTime = result.stringValue;
        }
        
        // Add to current bookings
        if (bookingCount < 4) {
          currentBookings[bookingCount] = {
            "slot" + String(i),
            phone,
            carNumber,
            endTime,
            0.0,
            false
          };
          bookingCount++;
        }
      }
    }
    
    Serial.println("Loaded " + String(bookingCount) + " existing bookings");
  } else {
    Serial.println("No existing bookings found");
  }
}

// ============ ORIGINAL FUNCTIONS ============

void setup() {
  Serial.begin(115200);
  
  // Initialize pins
  initializePins();
  
  // Initialize GSM
  initializeGSM();
  
  // Connect to WiFi
  connectToWiFi();
  
  // Initialize Firebase
  initializeFirebase();
  
  // Initialize booking tracking
  initializeBookings();
  
  Serial.println("System initialized successfully");
}

void loop() {
  if (Firebase.ready()) {
    unsigned long currentMillis = millis();
    
    // Update sensor data every 2 seconds
    if (currentMillis - sendDataPrevMillis > 2000) {
      sendDataPrevMillis = currentMillis;
      updateSensorData();
    }
    
    // Check bookings every 30 seconds
    if (currentMillis - checkBookingsPrevMillis > 30000) {
      checkBookingsPrevMillis = currentMillis;
      checkBookingStatus();
    }
    
    // Check payments every 60 seconds
    if (currentMillis - checkPaymentsPrevMillis > 60000) {
      checkPaymentsPrevMillis = currentMillis;
      checkPaymentStatus();
    }
  }
  
  handleGSMResponse();
  updateLEDs();
}

void initializePins() {
  // Ultrasonic sensors
  pinMode(TRIG_PIN_1, OUTPUT);
  pinMode(ECHO_PIN_1, INPUT);
  pinMode(TRIG_PIN_2, OUTPUT);
  pinMode(ECHO_PIN_2, INPUT);
  pinMode(TRIG_PIN_3, OUTPUT);
  pinMode(ECHO_PIN_3, INPUT);
  pinMode(TRIG_PIN_4, OUTPUT);
  pinMode(ECHO_PIN_4, INPUT);
  
  // GSM
  pinMode(GSM_POWER, OUTPUT);
  digitalWrite(GSM_POWER, HIGH);
  
  // LEDs
  pinMode(LED_GREEN, OUTPUT);
  pinMode(LED_RED, OUTPUT);
  pinMode(LED_BLUE, OUTPUT);
  
  // Initialize GSM serial
  gsmSerial.begin(9600, SERIAL_8N1, GSM_RX, GSM_TX);
}

void initializeGSM() {
  digitalWrite(GSM_POWER, LOW);
  delay(1000);
  digitalWrite(GSM_POWER, HIGH);
  delay(3000);
  
  sendATCommand("AT", 2000);
  sendATCommand("ATE0", 2000);
  sendATCommand("AT+CMGF=1", 2000);
  sendATCommand("AT+CNMI=2,2,0,0,0", 2000);
  
  if (sendATCommand("AT+CPIN?", 5000).indexOf("READY") != -1) {
    Serial.println("GSM Module initialized successfully");
    gsmReady = true;
    updateSystemStatus("GSM Ready");
  } else {
    Serial.println("GSM Module initialization failed");
    gsmReady = false;
    updateSystemStatus("GSM Failed");
  }
}

void connectToWiFi() {
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  Serial.print("Connecting to WiFi");
  while (WiFi.status() != WL_CONNECTED) {
    Serial.print(".");
    delay(300);
  }
  Serial.println("\nConnected with IP: " + WiFi.localIP().toString());
}

void initializeFirebase() {
  config.api_key = API_KEY;
  config.database_url = DATABASE_URL;
  
  auth.user.email = USER_EMAIL;
  auth.user.password = USER_PASSWORD;
  
  Firebase.begin(&config, &auth);
  Firebase.reconnectWiFi(true);
  
  Serial.println("Authenticating with Firebase...");
  while (!Firebase.ready()) {
    Serial.print(".");
    delay(1000);
  }
  Serial.println("\nFirebase authenticated successfully!");
}

void updateSensorData() {
  int distance1 = readUltrasonic(TRIG_PIN_1, ECHO_PIN_1);
  int distance2 = readUltrasonic(TRIG_PIN_2, ECHO_PIN_2);
  int distance3 = readUltrasonic(TRIG_PIN_3, ECHO_PIN_3);
  int distance4 = readUltrasonic(TRIG_PIN_4, ECHO_PIN_4);
  
  String status1 = determineStatus(distance1);
  String status2 = determineStatus(distance2);
  String status3 = determineStatus(distance3);
  String status4 = determineStatus(distance4);
  
  updateFirebaseSlot("slot1", status1, distance1);
  updateFirebaseSlot("slot2", status2, distance2);
  updateFirebaseSlot("slot3", status3, distance3);
  updateFirebaseSlot("slot4", status4, distance4);
  
  Serial.printf("Slots: 1-%dcm(%s) 2-%dcm(%s) 3-%dcm(%s) 4-%dcm(%s)\n",
                distance1, status1.c_str(), distance2, status2.c_str(),
                distance3, status3.c_str(), distance4, status4.c_str());
}

void checkBookingStatus() {
  for (int i = 0; i < bookingCount; i++) {
    if (currentBookings[i].slotId != "") {
      checkSlotBooking(currentBookings[i]);
    }
  }
}

void checkSlotBooking(BookingInfo &booking) {
  String path = "bookings/" + booking.slotId;
  
  if (Firebase.RTDB.getJSON(&fbdo, path.c_str())) {
    FirebaseJson *json = fbdo.jsonObjectPtr();
    FirebaseJsonData result;
    
    if (json->get(result, "bookedUntil")) {
      String endTime = result.stringValue;
      time_t endTimestamp = parseISO8601(endTime);
      time_t currentTime = getCurrentTime();
      
      if (currentTime > 0 && endTimestamp > 0) {
        time_t remainingTime = endTimestamp - currentTime;
        
        if (remainingTime <= 0 && !booking.paymentPending) {
          // Time expired, calculate charges
          calculateOvertimeCharges(booking);
        } else if (remainingTime <= 900) { // 15 minutes
          sendTimeWarning(booking, remainingTime);
        }
        
        // Update remaining time in Firebase
        updateRemainingTime(booking.slotId, remainingTime);
      }
    }
  }
}

void calculateOvertimeCharges(BookingInfo &booking) {
  String path = "bookings/" + booking.slotId;
  
  // Calculate overtime (simplified)
  float basePrice = 50.0;
  float overtimeHours = 2.0; // Example - in real implementation, calculate actual overtime
  float overtimeCharge = overtimeHours * basePrice * 2; // Double rate for overtime
  
  booking.amountDue = basePrice + overtimeCharge;
  booking.paymentPending = true;
  
  // Update Firebase
  FirebaseJson updateData;
  updateData.set("amountDue", booking.amountDue);
  updateData.set("paymentPending", true);
  updateData.set("overtimeHours", overtimeHours);
  updateData.set("status", "payment_pending");
  
  if (Firebase.RTDB.updateNode(&fbdo, path.c_str(), &updateData)) {
    Serial.println("Overtime charges calculated for " + booking.slotId);
    
    // Send payment request
    String message = "ALERT: Parking time exceeded for " + booking.carNumber + 
                    ". Amount due: ₹" + String(booking.amountDue, 2) + 
                    ". Please make payment to exit.";
    sendSMS(booking.phoneNumber, message);
    
    updateSystemStatus("Payment requested for " + booking.carNumber);
  }
}

void sendTimeWarning(BookingInfo &booking, time_t remainingTime) {
  int minutes = remainingTime / 60;
  String message = "REMINDER: Parking time for " + booking.carNumber + 
                  " expires in " + String(minutes) + " minutes.";
  sendSMS(booking.phoneNumber, message);
}

void checkPaymentStatus() {
  for (int i = 0; i < bookingCount; i++) {
    if (currentBookings[i].paymentPending) {
      checkSlotPayment(currentBookings[i]);
    }
  }
}

void checkSlotPayment(BookingInfo &booking) {
  String path = "bookings/" + booking.slotId;
  
  if (Firebase.RTDB.getJSON(&fbdo, path.c_str())) {
    FirebaseJson *json = fbdo.jsonObjectPtr();
    FirebaseJsonData result;
    
    if (json->get(result, "status")) {
      String status = result.stringValue;
      if (status == "completed") {
        // Payment completed, free the slot
        freeParkingSlot(booking.slotId);
        booking.paymentPending = false;
        
        String message = "Payment confirmed for " + booking.carNumber + 
                        ". You may now exit. Thank you!";
        sendSMS(booking.phoneNumber, message);
        
        // Remove from current bookings
        booking.slotId = "";
        updateSystemStatus("Payment completed for " + booking.carNumber);
      }
    }
  }
}

void freeParkingSlot(String slotId) {
  String path = "parkingSlots/" + slotId;
  
  FirebaseJson updateData;
  updateData.set("status", "available");
  updateData.set("bookedUntil", "");
  updateData.set("bookingId", "");
  updateData.set("carNumber", "");
  
  if (Firebase.RTDB.updateNode(&fbdo, path.c_str(), &updateData)) {
    Serial.println("Freed parking slot: " + slotId);
    updateSystemStatus("Slot " + slotId + " freed");
  }
}

void updateLEDs() {
  // Green: System normal
  // Red: Payment pending
  // Blue: GSM active
  
  bool paymentPending = false;
  for (int i = 0; i < bookingCount; i++) {
    if (currentBookings[i].paymentPending) {
      paymentPending = true;
      break;
    }
  }
  
  digitalWrite(LED_GREEN, !paymentPending);
  digitalWrite(LED_RED, paymentPending);
  digitalWrite(LED_BLUE, gsmReady);
}

void updateSystemStatus(String status) {
  String path = "system/status";
  if (Firebase.RTDB.setString(&fbdo, path.c_str(), status)) {
    Serial.println("System status updated: " + status);
  }
}

void updateRemainingTime(String slotId, time_t remainingTime) {
  String path = "bookings/" + slotId + "/remainingTime";
  
  if (Firebase.RTDB.setInt(&fbdo, path.c_str(), remainingTime)) {
    // Success - optional debug output
  }
}
