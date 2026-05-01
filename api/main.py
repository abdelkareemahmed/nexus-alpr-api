from fastapi import FastAPI, File, UploadFile, Form
from fastapi.responses import StreamingResponse
import cv2
import csv
from io import StringIO
import numpy as np
from ultralytics import YOLO
from api.database import init_db, log_entry, checkout_vehicle, add_new_subscriber, get_all_visits
from fastapi.middleware.cors import CORSMiddleware 

app = FastAPI(title="Smart Parking System API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

init_db()

print("Loading AI Models...")
plate_model = YOLO('models/plate_model.pt')
ocr_model = YOLO('models/ocr_model.pt')
print("Models Loaded Successfully!")

arabic_mapping = {
    'alef': 'أ', 'baa': 'ب', 'geem': 'ج', 'dal': 'د', 'raa': 'ر',
    'seen': 'س', 'saad': 'ص', 'taa': 'ط', 'ain': 'ع', 'faa': 'ف',
    'qaaf': 'ق', 'laam': 'ل', 'meem': 'م', 'noon': 'ن', 'haa': 'هـ',
    'waaw': 'و', 'waw': 'و', 'yaa': 'ي', 'kaaf': 'ك', 'ghain': 'غ', 
    'zaal':'ذ', 'zain':'ز'
}

@app.post("/process_vehicle")
async def process_vehicle(gate: str = Form(...), file: UploadFile = File(...)):
    
    if gate not in ['in', 'out']:
        return {"status": "error", "message": "Invalid gate type. Must be 'in' or 'out'."}

    contents = await file.read()
    nparr = np.frombuffer(contents, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    if img is None:
        return {"status": "error", "message": "Invalid image file provided."}

    plate_results = plate_model.predict(img, conf=0.5)
    
    detected_vehicles_list = []
    
    for plate_result in plate_results:
        boxes = plate_result.boxes
        if len(boxes) == 0: continue
            
        for box in boxes:
            x1, y1, x2, y2 = map(int, box.xyxy[0])
            plate_crop = img[y1:y2, x1:x2]
            plate_crop_zoomed = cv2.resize(plate_crop, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
            
            char_results = ocr_model.predict(plate_crop_zoomed, conf=0.25)
            detected_letters = []
            detected_numbers = []
            
            for char_result in char_results:
                for char_box in char_result.boxes:
                    char_x1 = char_box.xyxy[0][0].item()
                    char_id = int(char_box.cls[0].item())
                    char_name = arabic_mapping.get(ocr_model.names[char_id], ocr_model.names[char_id])
                    
                    if char_name.isdigit():
                        detected_numbers.append({'x': char_x1, 'name': char_name})
                    else:
                        detected_letters.append({'x': char_x1, 'name': char_name})
            
            detected_letters.sort(key=lambda item: item['x'], reverse=True)
            detected_numbers.sort(key=lambda item: item['x'], reverse=False)
            
            final_plate_text = f"{' '.join([c['name'] for c in detected_letters])} {''.join([n['name'] for n in detected_numbers])}".strip()
            
            if final_plate_text:
                db_response = {}
                
                if gate == 'in':
                    db_response = log_entry(final_plate_text)
                elif gate == 'out':
                    db_response = checkout_vehicle(final_plate_text)
                    
                detected_vehicles_list.append({
                    "plate_number": final_plate_text,
                    "database_response": db_response
                })

    if len(detected_vehicles_list) > 0:
        return {
            "status": "success", 
            "total_detected": len(detected_vehicles_list),
            "results": detected_vehicles_list
        }
    else:
        return {"status": "error", "message": "No clear license plates found in the image."}
    
@app.post("/add_vip")
def add_vip(plate_number: str = Form(...), owner_name: str = Form(...)):
    result = add_new_subscriber(plate_number, owner_name)
    return result

@app.get("/export_report")
def export_report():
    rows = get_all_visits()
    
    stream = StringIO()
    writer = csv.writer(stream)
    
    writer.writerow(["Plate Number", "Entry Time", "Exit Time", "Status", "Fee (EGP)"])
    
    for row in rows:
        writer.writerow(row)
        
    response = StreamingResponse(iter([stream.getvalue()]), media_type="text/csv")
    response.headers["Content-Disposition"] = "attachment; filename=nexus_daily_report.csv"
    
    return response